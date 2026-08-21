"""
Embedded HTTP REST & SSE Streaming Server for the Linux Ops Assistant GUI.
Zero external dependencies — standard library Python 3.9+ HTTP server.
"""

from __future__ import annotations

import os
import sys
import json
import time
import uuid
import queue
import shutil
import urllib.parse
import webbrowser
import threading
from pathlib import Path
from http import HTTPStatus
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from ops_assistant.agent import OpsAssistantAgent
from ops_assistant.collectors.hub import TelemetryHub
from ops_assistant.collectors.distro_detector import DistroDetector
from ops_assistant.tools.executor import SafeExecutor
from ops_assistant.tools.safety import CommandSafetyValidator
from ops_assistant.tools import desktop_ops, download_ops, storage_ops, process_ops, network_ops, log_ops
from ops_assistant.models import SafetyLevel


STATIC_DIR = Path(__file__).parent / "static"

# ---------------------------------------------------------------------------
# CommandCenter Session Store — thread-safe in-memory dict, 5-min TTL
# ---------------------------------------------------------------------------
_COMMAND_SESSIONS: Dict[str, Any] = {}
_SESSIONS_LOCK = threading.Lock()
_SESSION_TTL = 300  # seconds


def _create_session(data: Dict[str, Any]) -> str:
    session_id = str(uuid.uuid4())
    with _SESSIONS_LOCK:
        _COMMAND_SESSIONS[session_id] = {
            "created_at": time.time(),
            "events_queue": queue.Queue(),
            "events_log": [],
            **data,
        }
    return session_id


def _get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with _SESSIONS_LOCK:
        sess = _COMMAND_SESSIONS.get(session_id)
        if sess is None:
            return None
        if time.time() - sess.get("created_at", 0) > _SESSION_TTL:
            del _COMMAND_SESSIONS[session_id]
            return None
        return sess


class OpsAssistantHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    agent: OpsAssistantAgent = None
    hub: TelemetryHub = None
    executor: SafeExecutor = None

    def log_message(self, format, *args):
        # Suppress noisy access logs
        pass

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400):
        self._send_json({"error": message, "success": False}, status=status)

    def _read_json(self) -> Dict[str, Any]:
        try:
            content_len = int(self.headers.get("Content-Length", 0))
            if content_len > 0:
                raw = self.rfile.read(content_len).decode("utf-8")
                return json.loads(raw)
        except Exception:
            pass
        return {}

    def do_HEAD(self):
        self.do_GET()

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. Root & Static Files
        if path in ("/", "/index.html"):
            self._serve_static_file("index.html", "text/html")
            return
        elif path.startswith("/static/") or path.startswith("/assets/"):
            if path.startswith("/static/"):
                rel_name = path[len("/static/"):]
            else:
                rel_name = "assets/" + path[len("/assets/"):]
            ext = os.path.splitext(rel_name)[1].lower()
            mime_map = {
                ".css": "text/css",
                ".js": "application/javascript",
                ".html": "text/html",
                ".json": "application/json",
                ".svg": "image/svg+xml",
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".ico": "image/x-icon"
            }
            mime = mime_map.get(ext, "application/octet-stream")
            self._serve_static_file(rel_name, mime)
            return

        # 2. Server-Sent Events (SSE) Live Telemetry Stream
        elif path == "/api/stream/telemetry":
            self._handle_telemetry_sse()
            return

        # 3. REST API Endpoints
        elif path == "/api/health":
            distro_override = query.get("distro", [None])[0]
            snap = self.hub.get_health_snapshot(distro_override=distro_override)
            self._send_json(snap.to_dict())
            return

        elif path == "/api/services":
            services = self._get_services_list()
            self._send_json({"services": services, "count": len(services)})
            return

        elif path == "/api/processes":
            n = int(query.get("n", [50])[0])
            procs_res = process_ops.list_processes(sort_by="cpu", top_n=n)
            self._send_json({"processes": procs_res.get("processes", []), "count": len(procs_res.get("processes", []))})
            return

        elif path == "/api/storage/analysis":
            raw_path = query.get("path", ["/"])[0]
            snap = self.hub.get_health_snapshot()
            large_res = storage_ops.find_large_files(search_path=raw_path, threshold_mb=100, top_n=20)
            self._send_json({
                "disks": [asdict(d) if hasattr(d, "__dataclass_fields__") else d.__dict__ for d in snap.disks],
                "large_files": large_res.get("files", [])
            })
            return

        elif path == "/api/network/status":
            interfaces = network_ops.show_interfaces()
            ports = network_ops.show_listening_ports()
            fw = network_ops.show_firewall_rules()
            self._send_json({
                "interfaces": interfaces.get("interfaces", []),
                "ports": ports.get("ports", []),
                "firewall": fw
            })
            return

        elif path == "/api/taxonomy/scenarios":
            scenarios = []
            for item in self.agent.FAILURE_TAXONOMY:
                scenarios.append({
                    "id": item.get("id"),
                    "symptom": item.get("symptom"),
                    "root_cause": item.get("root_cause"),
                    "rationale": item.get("rationale"),
                    "commands": [
                        {
                            "command": cmd[0],
                            "safety_level": cmd[1].value if hasattr(cmd[1], "value") else str(cmd[1]),
                            "risk_score": cmd[2],
                            "rationale": cmd[3]
                        }
                        for cmd in item.get("commands", [])
                    ]
                })
            self._send_json({"scenarios": scenarios, "count": len(scenarios)})
            return

        elif path == "/api/hardware/profile":
            from ops_assistant.hardware.advisor import HardwareAdvisor
            adv = HardwareAdvisor().get_full_advisory()
            self._send_json(adv)
            return

        elif path == "/api/setup/status":
            from ops_assistant.hardware.advisor import HardwareAdvisor, MODEL_CATALOG
            from ops_assistant.model_manager.downloader import ModelDownloader
            from ops_assistant.config import get_config, is_setup_completed
            adv = HardwareAdvisor()
            prof = adv.profiler.profile()
            rec = adv.get_full_advisory()["recommended_model"]
            dl = ModelDownloader()
            cfg = get_config()
            self._send_json({
                "setup_completed": is_setup_completed(),
                "has_models": dl.has_any_model_installed(),
                "config": cfg,
                "hardware": prof.to_dict(),
                "recommended_model": rec,
                "catalog": MODEL_CATALOG,
                "installed_models": dl.list_available_models(),
                "download_progress": dl.get_download_progress()
            })
            return

        elif path == "/api/models/list":
            from ops_assistant.model_manager.downloader import ModelDownloader
            dl = ModelDownloader()
            active_p = dl.get_active_model_path()
            self._send_json({
                "models": dl.list_available_models(),
                "active_model_path": str(active_p) if active_p else None
            })
            return

        elif path == "/api/models/download/progress":
            from ops_assistant.model_manager.downloader import ModelDownloader
            dl = ModelDownloader()
            self._send_json({"downloads": dl.get_download_progress()})
            return

        elif path == "/api/proactive/audit":
            from ops_assistant.tools import proactive_engine
            res = proactive_engine.run_proactive_audit()
            self._send_json(res)
            return

        elif path == "/api/docker/status":
            from ops_assistant.tools import docker_ops
            containers = docker_ops.list_containers(all_containers=True)
            conflicts = docker_ops.inspect_container_conflicts()
            self._send_json({
                "containers": containers.get("containers", []),
                "conflicts": conflicts.get("conflicts", []),
                "count": containers.get("count", 0),
                "running_count": containers.get("running_count", 0),
                "failed_count": containers.get("failed_count", 0)
            })
            return

        elif path == "/api/security/audit":
            from ops_assistant.tools import security_ops
            res = security_ops.audit_security()
            self._send_json(res)
            return

        elif path == "/api/backups":
            from ops_assistant.tools import backup_ops
            res = backup_ops.list_backups()
            self._send_json(res)
            return

        elif path == "/api/system/boot":
            from ops_assistant.tools import system_ops
            res = system_ops.analyze_boot_time()
            self._send_json(res)
            return

        elif path == "/api/distro":
            detector = DistroDetector()
            d_info = detector.detect()
            self._send_json(d_info.to_dict() if hasattr(d_info, "to_dict") else d_info.__dict__)
            return

        elif path.startswith("/api/command/stream/"):
            session_id = path[len("/api/command/stream/"):]
            self._handle_command_stream_sse(session_id)
            return

        else:
            self._send_error("Endpoint not found", status=404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json()

        # 1. AI Agent Interactive Chat & Command Dispatch
        if path == "/api/agent/chat":
            prompt = body.get("prompt", "").strip()
            if not prompt:
                self._send_error("Prompt is required")
                return
            context = body.get("context", {})
            execute = bool(body.get("execute", True))
            result = self.agent.execute_agent_action(prompt, context=context, execute=execute)
            self._send_json(result)
            return

        # 2. Diagnostics
        elif path == "/api/diagnose":
            query = body.get("query", "").strip()
            distro_override = body.get("distro")
            if not query:
                self._send_error("Query is required")
                return
            report = self.agent.diagnose(query, distro_override=distro_override)
            self._send_json(report.to_dict())
            return

        # 3. Desktop Actions
        elif path == "/api/desktop/action":
            action = body.get("action")
            target_path = body.get("path", "~")
            url = body.get("url", "https://google.com")
            src = body.get("src", "")
            dst = body.get("dst", "")

            if action == "open_folder":
                res = desktop_ops.open_folder(target_path)
            elif action == "open_file":
                res = desktop_ops.open_file(target_path)
            elif action == "open_image":
                res = desktop_ops.open_image(target_path)
            elif action == "open_browser":
                res = desktop_ops.open_browser(url)
            elif action == "move_path":
                res = desktop_ops.move_path(src, dst)
            elif action == "copy_path":
                res = desktop_ops.copy_path(src, dst)
            elif action == "trash_path":
                res = desktop_ops.trash_path(target_path)
            else:
                res = {"success": False, "error": f"Unknown desktop action: {action}"}
            self._send_json(res)
            return

        # 4. Universal Downloader
        elif path == "/api/download":
            url = body.get("url", "").strip()
            dest_dir = body.get("destination_dir", "~/Downloads")
            filename = body.get("filename")
            auto_extract = bool(body.get("auto_extract", False))

            if not url:
                self._send_error("URL is required for download")
                return

            res = download_ops.download_file(
                url=url,
                destination_dir=dest_dir,
                filename=filename,
                auto_extract=auto_extract
            )
            self._send_json(res)
            return

        # 5. Service Controller
        elif path == "/api/services/action":
            svc = body.get("service", "").strip()
            action = body.get("action", "status").strip()
            if not svc:
                self._send_error("Service name required")
                return

            if action == "logs":
                res = log_ops.tail_log(service=svc, lines=100)
            elif action == "start":
                res = process_ops.start_service(svc)
            elif action == "stop":
                res = process_ops.stop_service(svc)
            elif action == "restart":
                res = process_ops.restart_service(svc)
            elif action == "reload":
                res = process_ops.reload_service(svc)
            elif action == "enable":
                res = process_ops.enable_service(svc)
            elif action == "disable":
                res = process_ops.disable_service(svc)
            elif action == "status":
                res = process_ops.show_service_status(svc)
            else:
                res = {"success": False, "error": f"Unknown service action: {action}"}
            self._send_json(res)
            return

        # 6. Process Kill
        elif path == "/api/processes/kill":
            pid = body.get("pid")
            sig = str(body.get("signal", "TERM"))
            if not pid:
                self._send_error("PID required")
                return
            res = process_ops.kill_process(pid=int(pid), signal=sig)
            self._send_json(res)
            return

        # 7. Storage Organisation & Cleaning
        elif path == "/api/storage/organise":
            target_path = body.get("path", "~/Downloads")
            dry_run = bool(body.get("dry_run", True))
            res = storage_ops.organise_directory(target_path, dry_run=dry_run)
            self._send_json(res)
            return

        elif path == "/api/storage/clean":
            dry_run = bool(body.get("dry_run", True))
            res = storage_ops.clean_logs(dry_run=dry_run)
            self._send_json(res)
            return

        # 8. Command Execution with AST Safety Guardrails & Sandbox Probe
        elif path == "/api/execute":
            command = body.get("command", "").strip()
            dry_run = bool(body.get("dry_run", False))
            if not command:
                self._send_error("Command required")
                return

            # Safety validation
            val = CommandSafetyValidator.validate(command)
            if val.level == SafetyLevel.DESTRUCTIVE:
                self._send_json({
                    "success": False,
                    "blocked": True,
                    "safety_level": val.level.value,
                    "risk_score": val.risk_score,
                    "error": f"DESTRUCTIVE command blocked: {val.matched_rule}",
                    "command": command
                }, status=403)
                return

            res = self.executor.execute(command, dry_run=dry_run)
            returncode = res.get("returncode", -1)
            self._send_json({
                "success": returncode == 0,
                "returncode": returncode,
                "stdout": res.get("stdout", ""),
                "stderr": res.get("stderr", ""),
                "latency_ms": res.get("elapsed_ms", 0.0),
                "command": command,
                "safety_level": val.level.value,
                "risk_score": val.risk_score,
                "dry_run": dry_run,
                "rollback_command": val.suggested_rollback
            })
            return

        # 9. Rollback Execution
        elif path == "/api/rollback":
            rollback_cmd = body.get("rollback_command", "").strip()
            if not rollback_cmd:
                self._send_error("Rollback command required")
                return
            res = self.executor.execute(rollback_cmd)
            returncode = res.get("returncode", -1)
            self._send_json({
                "success": returncode == 0,
                "returncode": returncode,
                "stdout": res.get("stdout", ""),
                "stderr": res.get("stderr", ""),
                "command": rollback_cmd
            })
            return

        # 10. Firewall Rule Update
        elif path == "/api/network/firewall":
            action = body.get("action")
            port = body.get("port")
            proto = body.get("proto", "tcp")
            if action == "allow" and port:
                res = network_ops.allow_port(port, proto)
            elif action == "deny" and port:
                res = network_ops.deny_port(port, proto)
            else:
                res = {"success": False, "error": "Invalid firewall parameters"}
            self._send_json(res)
            return

        # 11. Hardware Auto-Tune & Model Selection
        elif path == "/api/hardware/tune":
            from ops_assistant.hardware.advisor import HardwareAdvisor, ModelSelector
            from ops_assistant.model_manager.downloader import ModelDownloader
            adv = HardwareAdvisor()
            prof = adv.profiler.profile()
            rec = ModelSelector.recommend_model(prof)
            dl = ModelDownloader()
            if rec.get("download_required") and rec.get("model_key"):
                mkey = rec["model_key"]
                avail = dl.list_available_models()
                if mkey in avail and not avail[mkey]["is_downloaded"]:
                    try:
                        dl.download_model(mkey)
                    except Exception:
                        pass
            self._send_json({"success": True, "advisory": adv.get_full_advisory(), "recommended_model": rec})
            return

        # 11b. Setup Configuration Apply
        elif path == "/api/setup/apply":
            from ops_assistant.config import set_setup_completed, get_config
            from ops_assistant.hardware.advisor import MODEL_CATALOG, HardwareAdvisor
            from ops_assistant.model_manager.downloader import ModelDownloader
            provider = body.get("provider", "auto")
            model_key = body.get("model_key")
            adv = HardwareAdvisor()
            prof = adv.profiler.profile()
            caps = adv.generate_capability_matrix(prof)

            dl = ModelDownloader()
            model_path = None
            if model_key and model_key in MODEL_CATALOG:
                m_info = MODEL_CATALOG[model_key]
                p = dl.target_dir / m_info["filename"]
                if p.exists():
                    model_path = str(p)

            res_cfg = set_setup_completed(
                provider=provider,
                model_key=model_key,
                model_path=model_path,
                hardware_tier=prof.compute_tier,
                threads=caps.recommended_threads,
                ctx_size=caps.recommended_ctx_size,
                gpu_layers=caps.recommended_gpu_layers
            )
            self._send_json({"success": True, "config": res_cfg})
            return

        # 11c. Background Model Download
        elif path == "/api/models/download":
            from ops_assistant.model_manager.downloader import ModelDownloader
            mkey = body.get("model_key", "")
            force = bool(body.get("force", False))
            dl = ModelDownloader()
            res = dl.start_background_download(mkey, force=force)
            self._send_json(res)
            return

        # 12. Docker Actions
        elif path == "/api/docker/action":
            from ops_assistant.tools import docker_ops
            act = body.get("action")
            cid = body.get("container", "")
            if act == "restart":
                res = docker_ops.restart_container(cid)
            elif act == "logs":
                res = docker_ops.get_container_logs(cid, tail=body.get("tail", 100))
            elif act == "prune":
                res = docker_ops.prune_docker_resources(dry_run=bool(body.get("dry_run", True)))
            else:
                res = {"success": False, "error": f"Unknown docker action: {act}"}
            self._send_json(res)
            return

        # 13. Backup & Restore Actions
        elif path == "/api/backup/create":
            from ops_assistant.tools import backup_ops
            path_target = body.get("path", "/etc")
            dest = body.get("dest", "~/.ops_assistant/backups")
            res = backup_ops.create_backup(path_target, backup_dir=dest)
            self._send_json(res)
            return

        elif path == "/api/backup/restore":
            from ops_assistant.tools import backup_ops
            backup_file = body.get("backup_file", "")
            destination = body.get("destination", "")
            res = backup_ops.restore_backup(backup_file, destination)
            self._send_json(res)
            return

        # 14. System Maintenance Actions
        elif path == "/api/system/action":
            from ops_assistant.tools import system_ops
            act = body.get("action")
            if act == "vacuum_journal":
                res = system_ops.vacuum_journal(max_size=body.get("max_size", "200M"), dry_run=bool(body.get("dry_run", True)))
            elif act == "trim_ssds":
                res = system_ops.trim_ssds(dry_run=bool(body.get("dry_run", True)))
            elif act == "clean_packages":
                res = system_ops.clean_package_cache(dry_run=bool(body.get("dry_run", True)))
            else:
                res = {"success": False, "error": f"Unknown system action: {act}"}
            self._send_json(res)
            return

        # 15. CommandCenter — Intent interpretation (plan without execution)
        elif path == "/api/command/interpret":
            text = body.get("text", "").strip()
            if not text:
                self._send_error("text field is required")
                return
            interpretation = self.agent.interpret_command(text)
            session_id = _create_session({
                "text": text,
                "understanding": interpretation["understanding"],
                "plan_steps": interpretation["plan_steps"],
                "requires_confirmation": interpretation["requires_confirmation"],
                "safety_level": interpretation["safety_level"],
                "intent": interpretation["intent"],
            })
            self._send_json({
                "session_id": session_id,
                "understanding": interpretation["understanding"],
                "plan_steps": interpretation["plan_steps"],
                "requires_confirmation": interpretation["requires_confirmation"],
                "safety_level": interpretation["safety_level"],
                "intent": interpretation["intent"],
                "confidence": interpretation.get("confidence", 1.0),
            })
            return

        # 16. CommandCenter — Execute a confirmed plan, stream results via SSE
        elif path == "/api/command/execute":
            session_id = body.get("session_id", "").strip()
            confirmed = bool(body.get("confirmed", False))
            if not session_id:
                self._send_error("session_id is required")
                return
            sess = _get_session(session_id)
            if not sess:
                self._send_error("Session not found or expired", status=404)
                return
            # Server-side confirmation gate — HIGH_RISK / DESTRUCTIVE require confirmed=true
            if sess.get("requires_confirmation") and not confirmed:
                self._send_json({
                    "blocked": True,
                    "error": "This action requires explicit confirmation (HIGH_RISK or DESTRUCTIVE). "
                             "Set confirmed: true to proceed.",
                    "safety_level": sess.get("safety_level"),
                    "requires_confirmation": True,
                }, status=403)
                return
            # Launch execution in a background thread; results stream via SSE
            t = threading.Thread(
                target=self._execute_plan_async,
                args=(session_id, sess),
                daemon=True,
            )
            t.start()
            self._send_json({"success": True, "session_id": session_id, "message": "Execution started"})
            return

        else:
            self._send_error("Endpoint not found", status=404)

    def _serve_static_file(self, filename: str, mime: str):
        target = (STATIC_DIR / filename).resolve()
        resolved_static = STATIC_DIR.resolve()
        if not (target == resolved_static or target.is_relative_to(resolved_static)) or not target.exists() or not target.is_file():
            self._send_error("File not found", status=404)
            return

        try:
            with open(target, "rb") as f:
                content = f.read()
            content_type = f"{mime}; charset=utf-8" if ("text" in mime or "javascript" in mime or "json" in mime) else mime
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self._send_error(str(e), status=500)

    # ------------------------------------------------------------------
    # CommandCenter SSE stream — drains per-session event queue
    # ------------------------------------------------------------------
    def _handle_command_stream_sse(self, session_id: str):
        sess = _get_session(session_id)
        if not sess:
            self._send_error("Session not found or expired", status=404)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        q: queue.Queue = sess["events_queue"]
        # Replay any events already logged (client connected after execution started)
        for ev in list(sess.get("events_log", [])):
            evt_type = ev["type"]
            data_str = json.dumps(ev["data"])
            try:
                self.wfile.write(f"event: {evt_type}\ndata: {data_str}\n\n".encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

        try:
            while True:
                try:
                    event = q.get(timeout=25)
                except queue.Empty:
                    # Keepalive comment
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue

                if event is None:
                    # Sentinel — execution complete
                    self.wfile.write(b"event: done\ndata: {}\n\n")
                    self.wfile.flush()
                    break

                evt_type = event["type"]
                data_str = json.dumps(event["data"])
                self.wfile.write(f"event: {evt_type}\ndata: {data_str}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    # ------------------------------------------------------------------
    # CommandCenter plan executor — runs in a background thread
    # ------------------------------------------------------------------
    def _execute_plan_async(self, session_id: str, sess: Dict[str, Any]):
        import subprocess as _sp

        q: queue.Queue = sess["events_queue"]
        log: List[Dict[str, Any]] = sess["events_log"]

        def emit(evt_type: str, data: Dict[str, Any]):
            event = {"type": evt_type, "data": data, "ts": time.time()}
            log.append(event)
            q.put(event)

        # 1. Emit understanding
        emit("understanding", {"text": sess.get("understanding", "")})

        plan_steps: List[Dict[str, Any]] = sess.get("plan_steps", [])

        # 2. Emit all steps as "pending" first (so the stepper renders immediately)
        for step in plan_steps:
            emit("plan_step", {**step, "status": "pending"})

        # 3. Execute each step and stream status transitions
        for step in plan_steps:
            cmd = step.get("command", "").strip()
            emit("plan_step", {**step, "status": "running"})

            if not cmd or cmd.startswith("ops-assistant "):
                # No real shell command — treat as instant success
                emit("plan_step", {**step, "status": "done", "exit_code": 0, "output": "Completed (no shell command)"})
                continue

            try:
                proc = _sp.run(
                    cmd, shell=True, capture_output=True, text=True, timeout=30
                )
                status = "done" if proc.returncode == 0 else "failed"
                output = (proc.stdout + proc.stderr).strip()
                emit("plan_step", {**step, "status": status, "exit_code": proc.returncode, "output": output[:2000]})
            except _sp.TimeoutExpired:
                emit("plan_step", {**step, "status": "failed", "exit_code": -1, "output": "Command timed out after 30 s"})
            except Exception as exc:
                emit("plan_step", {**step, "status": "failed", "exit_code": -1, "output": str(exc)})

        # 4. Build final result from log
        done_count = sum(1 for e in log if e["type"] == "plan_step" and e["data"].get("status") == "done")
        fail_count = sum(1 for e in log if e["type"] == "plan_step" and e["data"].get("status") == "failed")
        raw_output = "\n".join(
            e["data"].get("output", "") for e in log
            if e["type"] == "plan_step" and e["data"].get("status") in ("done", "failed") and e["data"].get("output")
        )

        if not plan_steps:
            summary = "No executable steps were generated for this command."
            success = True
        elif fail_count == 0:
            summary = (
                f"All {done_count} step(s) completed successfully."
                if done_count > 1
                else "Step completed successfully."
            )
            success = True
        else:
            summary = f"{done_count} step(s) completed, {fail_count} failed."
            success = False

        emit("result", {
            "success": success,
            "summary": summary,
            "raw_output": raw_output,
            "exit_code": 0 if success else 1,
        })

        # Sentinel to signal SSE client the stream is complete
        q.put(None)

    def _handle_telemetry_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        try:
            while True:
                snap = self.hub.get_health_snapshot()
                data_str = json.dumps(snap.to_dict())
                self.wfile.write(f"data: {data_str}\n\n".encode("utf-8"))
                self.wfile.flush()
                time.sleep(1.5)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _get_services_list(self) -> List[Dict[str, Any]]:
        services = []
        if shutil.which("systemctl"):
            try:
                import subprocess
                p = subprocess.run(
                    ["systemctl", "list-units", "--type=service", "--all", "--no-legend", "--no-pager"],
                    capture_output=True, text=True, timeout=5
                )
                for line in p.stdout.strip().splitlines()[:100]:
                    parts = line.strip().split(None, 4)
                    if len(parts) >= 4:
                        unit = parts[0]
                        load = parts[1]
                        active = parts[2]
                        sub = parts[3]
                        desc = parts[4] if len(parts) > 4 else ""
                        services.append({
                            "unit": unit,
                            "load": load,
                            "active": active,
                            "sub": sub,
                            "description": desc
                        })
            except Exception:
                pass
        return services


def start_gui_server(
    host: str = "127.0.0.1",
    port: int = 8888,
    open_browser: bool = True,
    agent: Optional[OpsAssistantAgent] = None
) -> Tuple[ThreadingHTTPServer, str]:
    """
    Start the embedded GUI server in a background thread or main loop.
    Returns (server_instance, url).
    """
    if agent is None:
        agent = OpsAssistantAgent()

    hub = agent.hub if hasattr(agent, "hub") else TelemetryHub()
    executor = SafeExecutor()

    OpsAssistantHandler.agent = agent
    OpsAssistantHandler.hub = hub
    OpsAssistantHandler.executor = executor

    # Find available port if specified port is in use
    server = None
    actual_port = port
    for p in range(port, port + 50):
        try:
            server = ThreadingHTTPServer((host, p), OpsAssistantHandler)
            actual_port = p
            break
        except OSError:
            continue

    if server is None:
        raise RuntimeError(f"Could not bind GUI server to any port in range {port}-{port+50}")

    url = f"http://{host}:{actual_port}"
    print(f"[*] AI Linux Ops Assistant GUI running at: {url}")

    if open_browser:
        try:
            webbrowser.open(url, new=2)
        except Exception:
            pass

    return server, url