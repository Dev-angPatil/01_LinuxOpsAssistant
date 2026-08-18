"""Agentic Diagnostic Loop for Linux Operations Assistant with Causal DAG and Sandbox Verification."""

import os
import re
import json
import time
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Tuple
from ops_assistant.models import (
    DiagnosticReport, XAIExplanation, SystemHealthSnapshot, SafetyLevel, LogRecord
)
from ops_assistant.collectors.hub import TelemetryHub
from ops_assistant.explainer.xai import XAIExplainer
from ops_assistant.explainer.causality_dag import CausalityDAGEngine, CausalityGraphResult
from ops_assistant.tools.safety import CommandSafetyValidator
from ops_assistant.tools.sandbox_probe import EphemeralSandboxProbe

class LLMProvider:
    """Base class for pluggable LLM inference backends."""
    def generate_diagnosis(self, query: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

class OllamaProvider(LLMProvider):
    def __init__(self, endpoint: str = "http://localhost:11434/api/generate", model: str = "llama3:8b"):
        self.endpoint = endpoint
        self.model = model

    def generate_diagnosis(self, query: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        prompt = (
            f"You are an expert Linux System Administrator AI. Diagnose the following query given system telemetry and logs.\n"
            f"Query: {query}\n"
            f"Context: {json.dumps(context)}\n"
            f"Respond ONLY in valid JSON with keys: symptom, root_cause, rationale, proposed_commands (list of tuples: [command, safety_level, risk_score, rationale]), confidence."
        )
        try:
            req_data = json.dumps({"model": self.model, "prompt": prompt, "stream": False, "format": "json"}).encode("utf-8")
            req = urllib.request.Request(self.endpoint, data=req_data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return json.loads(data.get("response", "{}"))
        except Exception:
            return None

class OpsAssistantAgent:
    COMMON_SERVICES = [
        "nginx", "apache2", "docker", "postgres", "postgresql", "mysql",
        "redis", "systemd-resolved", "ssh", "sshd", "kubelet", "cron", "named",
        "chrony", "timesyncd", "ufw", "iptables"
    ]

    FAILURE_TAXONOMY = [
        {
            "id": "PORT_CONFLICT",
            "pattern": r"(Address already in use|bind\(\) to .* failed|port \d+ already in use|EADDRINUSE)",
            "symptom": "Service failed to bind to target TCP/UDP socket.",
            "root_cause": "The configured listening port is already bound by another active process.",
            "commands": [
                ("sudo ss -tulpn | grep -E ':(80|443|8080|5432|3306|6379|22)'", SafetyLevel.READ_ONLY, 0.05, "Inspect which PID currently holds the listening port descriptor."),
                ("sudo systemctl status {service}", SafetyLevel.READ_ONLY, 0.05, "Inspect systemd unit exit status and error journal slice.")
            ],
            "rationale": "Socket collisions prevent daemons from starting. You must either terminate the colliding process or reconfigure the service port."
        },
        {
            "id": "PERMISSION_DENIED",
            "pattern": r"(Permission denied|EACCES|Failed to open .*: Permission denied|could not open directory|access denied for user)",
            "symptom": "File, socket or path access blocked by filesystem permissions.",
            "root_cause": "The service process user does not possess POSIX read/write permissions for the designated path.",
            "commands": [
                ("ls -la /var/log/{service} /etc/{service}", SafetyLevel.READ_ONLY, 0.05, "Check user, group, and mode bits on service paths."),
                ("sudo chown -R {service}:{service} /var/log/{service}", SafetyLevel.MODIFYING, 0.40, "Restore expected service ownership to log directory.")
            ],
            "rationale": "Daemon processes dropped privileges to service accounts (e.g. www-data, postgres) and cannot access root-owned paths."
        },
        {
            "id": "OOM_KILL",
            "pattern": r"(Out of memory|Killed process \d+|oom-killer|invoked oom-killer|fatal error: runtime: out of memory|Memory cgroup out of memory)",
            "symptom": "Process terminated by Linux kernel Out-of-Memory (OOM) killer.",
            "root_cause": "Linux kernel Out-of-Memory (OOM) killer terminated the process due to exhausted system RAM + Swap or exceeded cgroup memory limit.",
            "commands": [
                ("free -h", SafetyLevel.READ_ONLY, 0.05, "Check current physical RAM and swap partition availability."),
                ("ps aux --sort=-%mem | head -n 10", SafetyLevel.READ_ONLY, 0.05, "Identify the top 10 memory-consuming processes."),
                ("dmesg -T --level=err,crit | tail -n 20", SafetyLevel.READ_ONLY, 0.05, "Inspect exact kernel OOM invocation logs and killed process PIDs.")
            ],
            "rationale": "Kernel killed the process to prevent an unrecoverable kernel panic when page allocation failed."
        },
        {
            "id": "DISK_EXHAUSTION",
            "pattern": r"(No space left on device|ENOSPC|disk full|write error: No space)",
            "symptom": "Disk write failure due to 0 remaining blocks or exhausted partition capacity.",
            "root_cause": "Target partition has exhausted available physical disk blocks.",
            "commands": [
                ("df -h", SafetyLevel.READ_ONLY, 0.05, "Verify disk partition block utilization across all mounts."),
                ("sudo du -sh /var/log/* /var/tmp/* /tmp/* 2>/dev/null | sort -rh | head -n 10", SafetyLevel.READ_ONLY, 0.05, "Pinpoint the largest log or temp files consuming disk space."),
                ("sudo journalctl --vacuum-size=200M", SafetyLevel.MODIFYING, 0.30, "Vacuum older systemd journal logs to reclaim disk space.")
            ],
            "rationale": "Logging, cache, or database write failed because the filesystem cannot allocate additional extents."
        },
        {
            "id": "INODE_EXHAUSTION",
            "pattern": r"(No space left on device: inode|cannot create directory: No space|out of inodes|structure needs cleaning)",
            "symptom": "Filesystem metadata exhaustion (0 available inodes despite free block space).",
            "root_cause": "Target filesystem inode allocation table has zero remaining entries due to millions of micro-files or session caches.",
            "commands": [
                ("df -i", SafetyLevel.READ_ONLY, 0.05, "Verify inode allocation table availability across all mounted partitions."),
                ("sudo find /var/spool /tmp /var/tmp -xdev -printf '%h\n' | sort | uniq -c | sort -k 1 -n | tail -n 10", SafetyLevel.READ_ONLY, 0.05, "Pinpoint directory trees hoarding excessive file counts.")
            ],
            "rationale": "Every file requires an inode entry; massive collections of tiny session files deplete inodes while disk blocks appear free."
        },
        {
            "id": "CONFIG_SYNTAX_ERROR",
            "pattern": r"(syntax error|directive .* is not allowed here|unknown directive|Configuration file .* test failed|failed to parse|invalid configuration)",
            "symptom": "Service configuration file parsing error.",
            "root_cause": "Syntax error, missing closing bracket, or unsupported directive in service configuration file.",
            "commands": [
                ("sudo nginx -t", SafetyLevel.READ_ONLY, 0.05, "Test NGINX configuration syntax and line numbers."),
                ("sudo journalctl -u {service} -n 30 --no-pager", SafetyLevel.READ_ONLY, 0.05, "View recent daemon config parser error messages.")
            ],
            "rationale": "Daemon aborts initialization before binding sockets when syntax validation fails."
        },
        {
            "id": "SSL_CERT_ERROR",
            "pattern": r"(certificate has expired|SSL_ERROR_SSL|certificate verify failed|certificate signed by unknown authority|certificate expired|SSL handshake failed|SSL routines:.*:certificate)",
            "symptom": "TLS handshake failure due to expired, mismatched, or untrusted SSL/TLS certificate.",
            "root_cause": "The active SSL/TLS X.509 certificate passed its Not-After expiration date or lacks valid intermediate CA chains.",
            "commands": [
                ("openssl x509 -enddate -noout -in /etc/ssl/certs/ssl-cert-snakeoil.pem", SafetyLevel.READ_ONLY, 0.05, "Check exact expiry timestamp of local SSL certificate."),
                ("sudo certbot certificates", SafetyLevel.READ_ONLY, 0.05, "Audit status of all Let's Encrypt managed SSL certificates."),
                ("sudo certbot renew --dry-run", SafetyLevel.READ_ONLY, 0.05, "Test automatic TLS certificate renewal pipeline.")
            ],
            "rationale": "Modern clients terminate TLS connections immediately upon encountering expired or invalid certificate chains."
        },
        {
            "id": "DNS_RESOLUTION_FAILURE",
            "pattern": r"(Temporary failure in name resolution|Could not resolve host|EAI_NONAME|Name or service not known|nameserver failure|systemd-resolved.*failed)",
            "symptom": "Domain name resolution failure (DNS lookup timeout or SERVFAIL).",
            "root_cause": "Upstream DNS resolvers are unreachable, `/etc/resolv.conf` is misconfigured, or `systemd-resolved` cache is stalled.",
            "commands": [
                ("resolvectl status", SafetyLevel.READ_ONLY, 0.05, "Inspect active DNS link upstream servers and query statistics."),
                ("cat /etc/resolv.conf", SafetyLevel.READ_ONLY, 0.05, "Inspect active nameserver directives in resolver configuration."),
                ("sudo systemd-resolve --flush-caches", SafetyLevel.MODIFYING, 0.20, "Flush stale DNS query cache.")
            ],
            "rationale": "System cannot translate domain names into IP addresses, causing network timeouts for external APIs and services."
        },
        {
            "id": "DPKG_LOCK_BLOCKED",
            "pattern": r"(Could not get lock /var/lib/dpkg/lock|Resource temporarily unavailable|dpkg: error: dpkg frontend lock is held|Unable to acquire the dpkg frontend lock|Could not open lock file /var/lib/apt/lists/lock)",
            "symptom": "Package manager execution blocked by another running apt/dpkg instance.",
            "root_cause": "An automated background unattended-upgrades job or another package manager session holds the exclusive dpkg frontend lock.",
            "commands": [
                ("sudo lsof /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock", SafetyLevel.READ_ONLY, 0.05, "Identify the active PID holding the dpkg lock descriptor."),
                ("sudo ps aux | grep -E 'apt|dpkg|unattended-upgrade'", SafetyLevel.READ_ONLY, 0.05, "Inspect running package manager processes."),
                ("sudo dpkg --configure -a", SafetyLevel.HIGH_RISK, 0.70, "Cleanly resume and repair pending package installation states.")
            ],
            "rationale": "Debian/Ubuntu package management uses advisory locks to guarantee atomic database updates."
        },
        {
            "id": "SYSTEMD_CRASH_LOOP",
            "pattern": r"(Start request repeated too quickly|Unit .* entered failed state|Failed with result 'exit-code'|Main process exited, code=dumped|Holdoff time finished, scheduling restart)",
            "symptom": "Systemd unit entered crash loop and exceeded restart burst limit (`StartLimitBurst`).",
            "root_cause": "Service crashed immediately upon boot repeatedly, triggering systemd rate-limiting backoff to protect CPU.",
            "commands": [
                ("sudo systemctl status {service} -l --no-pager", SafetyLevel.READ_ONLY, 0.05, "Inspect full failure callstack and unit properties."),
                ("sudo journalctl -u {service} -xeu {service} -n 40 --no-pager", SafetyLevel.READ_ONLY, 0.05, "Inspect crash error messages with systemd catalog explanations."),
                ("sudo systemctl reset-failed {service}", SafetyLevel.MODIFYING, 0.30, "Reset the rate-limit failure counter on the unit.")
            ],
            "rationale": "Systemd suspends automatic restarts when `StartLimitBurst` is breached to prevent spinning CPU cores."
        },
        {
            "id": "DB_CONN_EXHAUSTION",
            "pattern": r"(too many connections|remaining connection slots are reserved|Connection pool exhausted|max_connections exceeded|Can't connect to MySQL server|server closed the connection unexpectedly)",
            "symptom": "Database connection pool saturated (clients receiving connection refused).",
            "root_cause": "Active concurrent client connections reached database `max_connections` limit or file descriptor `ulimit`.",
            "commands": [
                ("sudo ss -tan state established '( dport = :5432 or dport = :3306 or dport = :6379 )' | wc -l", SafetyLevel.READ_ONLY, 0.05, "Count total active established database client connections."),
                ("sudo systemctl status postgresql mysql redis", SafetyLevel.READ_ONLY, 0.05, "Inspect database daemon health status.")
            ],
            "rationale": "Database engines reject new connection requests once backend worker limits or OS socket descriptors are exhausted."
        },
        {
            "id": "FIREWALL_PORT_BLOCKED",
            "pattern": r"(Connection refused|Connection timed out.*port|Host unreachable|No route to host|iptables: DROP|UFW BLOCK|filtered port)",
            "symptom": "Network ingress or egress traffic dropped by kernel packet filter.",
            "root_cause": "Firewall rules (UFW / iptables / nftables) are dropping packets targeting the specified port or IP range.",
            "commands": [
                ("sudo ufw status verbose", SafetyLevel.READ_ONLY, 0.05, "Check active UFW firewall rule configuration and status."),
                ("sudo iptables -L -n -v --line-numbers", SafetyLevel.READ_ONLY, 0.05, "Inspect low-level netfilter chains and dropped packet counters."),
                ("sudo ufw allow 80/tcp", SafetyLevel.HIGH_RISK, 0.70, "Allow HTTP traffic through UFW firewall.")
            ],
            "rationale": "Default-drop firewall policies isolate unconfigured ports to prevent unauthorized remote network access."
        },
        {
            "id": "ZOMBIE_PROCESS_ACCUMULATION",
            "pattern": r"(defunct|zombie process|defunct process accumulating|maximum number of processes reached|fork: Resource temporarily unavailable)",
            "symptom": "Process table saturated by defunct zombie child processes.",
            "root_cause": "Parent processes terminated or failed to invoke `wait()`/`waitpid()` on exited children, causing zombie PID accumulation.",
            "commands": [
                ("ps aux | awk '{if ($8 ~ /Z/) print $0}'", SafetyLevel.READ_ONLY, 0.05, "List all current defunct zombie processes with their PIDs."),
                ("ps -ef | grep defunct | head -n 10", SafetyLevel.READ_ONLY, 0.05, "Identify parent PIDs responsible for uncollected zombie children.")
            ],
            "rationale": "Zombies occupy PID slots in the kernel process table without consuming RAM until their parent is terminated."
        },
        {
            "id": "IOWAIT_BOTTLENECK",
            "pattern": r"(high\s+iowait|iowait.*high|task .* blocked for more than \d+ seconds|blk_update_request: I/O error|Buffer I/O error on dev|high disk latency|iowait\s+spike)",
            "symptom": "High kernel CPU I/O wait state causing sluggish system response.",
            "root_cause": "Disk block layer is bottlenecked by saturated write throughput, degrading storage drive, or failing hardware controller.",
            "commands": [
                ("iostat -x 1 3", SafetyLevel.READ_ONLY, 0.05, "Inspect device await, r/s, w/s, and disk %utilization."),
                ("dmesg -T --level=err,crit | grep -i -E 'i/o|ata|nvme|scsi|error'", SafetyLevel.READ_ONLY, 0.05, "Inspect kernel ring buffer for disk hardware errors.")
            ],
            "rationale": "Processes enter uninterruptible sleep ('D' state) while waiting for slow or unresponsive storage controllers."
        },
        {
            "id": "SELINUX_APPARMOR_DENIAL",
            "pattern": r"(type=AVC msg=audit|apparmor=\"DENIED\"|avc:\s+denied|permission=requested_mask|audit: type=1400)",
            "symptom": "Mandatory Access Control (MAC) security policy denial.",
            "root_cause": "SELinux or AppArmor security profile prevented service executable from reading/writing confined resources.",
            "commands": [
                ("sudo aa-status", SafetyLevel.READ_ONLY, 0.05, "Check AppArmor profile status and confined applications."),
                ("sudo dmesg -T | grep -i -E 'apparmor|audit|avc' | tail -n 20", SafetyLevel.READ_ONLY, 0.05, "Inspect exact security policy violation audit records.")
            ],
            "rationale": "Linux Security Modules (LSM) enforce least-privilege security profiles overriding standard DAC permissions."
        },
        {
            "id": "NTP_CLOCK_DRIFT",
            "pattern": r"(Time has been changed|Server has gone too long without receiving time|system clock desynchronized|NTP sync failed|clock skew detected)",
            "symptom": "System clock drift desynchronizing authentication tokens and TLS certificates.",
            "root_cause": "Network Time Protocol (NTP) service is stopped, blocked by firewall, or upstream time servers are unreachable.",
            "commands": [
                ("timedatectl status", SafetyLevel.READ_ONLY, 0.05, "Check local RTC time, UTC time, and NTP synchronization state."),
                ("timedatectl timesync-status", SafetyLevel.READ_ONLY, 0.05, "Inspect upstream time server jitter, delay, and offset."),
                ("sudo timedatectl set-ntp true", SafetyLevel.MODIFYING, 0.35, "Enable automatic systemd network time synchronization.")
            ],
            "rationale": "Clock drift breaks Kerberos tokens, JWT signatures, SSL certificate validation, and distributed clustering."
        }
    ]

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.hub = TelemetryHub()
        self.explainer = XAIExplainer()
        self.causality_engine = CausalityDAGEngine()
        self.sandbox_probe = EphemeralSandboxProbe()
        self.safety_validator = CommandSafetyValidator()
        self.llm_provider = llm_provider

    def extract_subsystem(self, query: str) -> Optional[str]:
        query_lower = query.lower()
        for svc in self.COMMON_SERVICES:
            if svc in query_lower:
                return svc
        return None

    def diagnose(
        self,
        query: str,
        custom_logs: Optional[List[LogRecord]] = None
    ) -> DiagnosticReport:
        start_time = time.perf_counter()
        subsystem = self.extract_subsystem(query)

        # 1. Telemetry Snapshot (Procfs + Systemd + Kernel PSI)
        health = self.hub.get_health_snapshot()

        # 2. Collect Logs across all sources
        if custom_logs is not None:
            logs = custom_logs
        else:
            logs = self.hub.journal.query_all_relevant_logs(
                unit=f"{subsystem}.service" if subsystem else None,
                subsystem=subsystem,
                lines=50
            )

        # Combine text for pattern search and causality DAG
        log_messages = [l.message for l in logs]
        combined_text = query + "\n" + "\n".join(log_messages)

        # 3. Build Dynamic Causality DAG from Ingested Logs
        dag_result = self.causality_engine.build_dag_from_events(log_messages)

        # 4. Match Failure Taxonomy (Neuro-Symbolic Rules)
        matched_item = None
        evidence: List[str] = []

        for item in self.FAILURE_TAXONOMY:
            matches = re.findall(item["pattern"], combined_text, flags=re.IGNORECASE)
            if matches:
                matched_item = item
                for l in logs:
                    if re.search(item["pattern"], l.message, flags=re.IGNORECASE):
                        evidence.append(f"[{l.source}] {l.message}")
                break

        svc_name = subsystem or "systemd"

        # 5. Optional LLM inference if configured
        if self.llm_provider and not matched_item:
            context = {
                "subsystem": svc_name,
                "pressure_status": health.pressure_status,
                "recent_logs": [l.message for l in logs[:10]],
                "causality_root": dag_result.summary
            }
            llm_res = self.llm_provider.generate_diagnosis(query, context)
            if llm_res and "symptom" in llm_res:
                xai = self.explainer.synthesize_xai(
                    symptom=llm_res.get("symptom", "LLM-detected system anomaly"),
                    root_cause=llm_res.get("root_cause", "Anomaly identified via LLM inference"),
                    evidence_logs=evidence if evidence else [f"[{l.source}] {l.message}" for l in logs[:2]],
                    commands=[
                        (cmd[0], SafetyLevel(cmd[1]) if cmd[1] in SafetyLevel.__members__ else SafetyLevel.READ_ONLY, float(cmd[2]), cmd[3])
                        for cmd in llm_res.get("proposed_commands", [])
                    ],
                    rationale=llm_res.get("rationale", "LLM reasoning explanation."),
                    confidence=float(llm_res.get("confidence", 0.90))
                )
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return DiagnosticReport(
                    query=query,
                    target_subsystem=subsystem,
                    health_snapshot=health,
                    explanation=xai,
                    causality_dag=dag_result.to_dict(),
                    latency_ms=round(elapsed_ms, 2),
                    reasoning_engine="LLM-Augmented-Causality-XAI"
                )

        if matched_item:
            symptom = matched_item["symptom"]
            root_cause = matched_item["root_cause"]
            rationale = matched_item["rationale"]
            # Format commands with service name
            raw_cmds = [
                (cmd[0].replace("{service}", svc_name), cmd[1], cmd[2], cmd[3])
                for cmd in matched_item["commands"]
            ]
        else:
            symptom = f"Unclassified anomaly detected on {svc_name}."
            root_cause = "General service startup or operational failure."
            rationale = "Inspect recent service logs and process state to identify failure root cause."
            raw_cmds = [
                (f"sudo journalctl -u {svc_name} -n 50 --no-pager", SafetyLevel.READ_ONLY, 0.05, "Retrieve recent systemd service logs."),
                (f"systemctl status {svc_name}", SafetyLevel.READ_ONLY, 0.05, "Inspect unit status and active process ID.")
            ]
            if not evidence and logs:
                evidence = [f"[{l.source}] {l.message}" for l in logs[:2]]

        # 6. Synthesize XAI Explanation
        xai = self.explainer.synthesize_xai(
            symptom=symptom,
            root_cause=root_cause,
            evidence_logs=evidence if evidence else ["No specific error logs matched; general triage initiated."],
            commands=raw_cmds,
            rationale=rationale,
            confidence=0.96 if matched_item else 0.80
        )

        # 7. Dry-Run Ephemeral Namespace Probe on Proposed Commands
        for cmd_prop in xai.proposed_commands:
            probe_res = self.sandbox_probe.verify_command(cmd_prop.command)
            cmd_prop.sandbox_verified = probe_res.is_verified

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        return DiagnosticReport(
            query=query,
            target_subsystem=subsystem,
            health_snapshot=health,
            explanation=xai,
            causality_dag=dag_result.to_dict(),
            latency_ms=round(elapsed_ms, 2),
            reasoning_engine="NeuroSymbolic-Causality-XAI"
        )
