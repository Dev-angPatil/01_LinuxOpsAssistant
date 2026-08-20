"""
Docker & Container Operations for Linux Ops Assistant.

Provides container health inspection, log streaming, auto-restarts,
dangling image/volume pruning with dry-run protection, and port conflict isolation.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple


def _docker_available() -> bool:
    return bool(shutil.which("docker"))


def _run_docker(args: List[str], timeout: int = 15) -> Tuple[int, str, str]:
    if not _docker_available():
        return 127, "", "Docker CLI not installed on this system."
    try:
        p = subprocess.run(["docker"] + args, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        return 124, "", f"Docker command timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def list_containers(all_containers: bool = True) -> Dict[str, Any]:
    """List all containers with status, image, ports, and names."""
    if not _docker_available():
        return {"success": False, "error": "Docker is not installed.", "containers": [], "count": 0}

    args = ["ps", "--format", "{{json .}}"]
    if all_containers:
        args.append("-a")

    rc, stdout, stderr = _run_docker(args)
    if rc != 0:
        return {"success": False, "error": stderr or "Failed to list containers.", "containers": [], "count": 0}

    containers = []
    for line in stdout.strip().splitlines():
        if line.strip():
            try:
                data = json.loads(line)
                containers.append({
                    "id": data.get("ID", ""),
                    "image": data.get("Image", ""),
                    "status": data.get("Status", ""),
                    "state": data.get("State", ""),
                    "names": data.get("Names", ""),
                    "ports": data.get("Ports", ""),
                    "created": data.get("CreatedAt", "")
                })
            except Exception:
                pass

    return {
        "success": True,
        "containers": containers,
        "count": len(containers),
        "running_count": sum(1 for c in containers if "running" in c.get("state", "").lower() or "up" in c.get("status", "").lower()),
        "failed_count": sum(1 for c in containers if "exited" in c.get("status", "").lower() or "dead" in c.get("state", "").lower())
    }


def get_container_logs(container_id_or_name: str, tail: int = 100) -> Dict[str, Any]:
    """Retrieve recent logs from a container."""
    if not _docker_available():
        return {"success": False, "error": "Docker is not installed."}

    rc, stdout, stderr = _run_docker(["logs", f"--tail={tail}", container_id_or_name])
    combined = f"{stdout}\n{stderr}".strip()
    return {
        "success": rc == 0,
        "container": container_id_or_name,
        "logs": combined,
        "lines_count": len(combined.splitlines()),
        "error": stderr if rc != 0 else None
    }


def restart_container(container_id_or_name: str) -> Dict[str, Any]:
    """Restart a container safely."""
    if not _docker_available():
        return {"success": False, "error": "Docker is not installed."}

    rc, stdout, stderr = _run_docker(["restart", container_id_or_name], timeout=30)
    return {
        "success": rc == 0,
        "container": container_id_or_name,
        "message": f"Successfully restarted container '{container_id_or_name}'" if rc == 0 else stderr,
        "error": stderr if rc != 0 else None,
        "rollback_command": f"docker stop '{container_id_or_name}'"
    }


def prune_docker_resources(dry_run: bool = True) -> Dict[str, Any]:
    """Prune dangling images, builder cache, and stopped containers."""
    if not _docker_available():
        return {"success": False, "error": "Docker is not installed."}

    # Estimate space via docker system df
    rc, stdout, _ = _run_docker(["system", "df", "--format", "{{json .}}"])
    df_info = []
    if rc == 0:
        for line in stdout.strip().splitlines():
            try:
                df_info.append(json.loads(line))
            except Exception:
                pass

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "message": "Simulated Docker cleanup. Run with dry_run=False to reclaim disk space.",
            "estimated_reclaimable": df_info,
            "proposed_command": "docker system prune -f"
        }

    rc, stdout, stderr = _run_docker(["system", "prune", "-f"])
    return {
        "success": rc == 0,
        "dry_run": False,
        "output": stdout.strip(),
        "message": "Successfully pruned unused Docker resources." if rc == 0 else stderr,
        "error": stderr if rc != 0 else None
    }


def inspect_container_conflicts() -> Dict[str, Any]:
    """Check for host port collisions and failed container crash loops."""
    res = list_containers(all_containers=True)
    if not res.get("success"):
        return {"conflicts": [], "crashed_containers": []}

    crashed = []
    ports_mapped: Dict[str, str] = {}
    collisions = []

    for c in res.get("containers", []):
        st = c.get("status", "").lower()
        if "exited (1" in st or "dead" in st or "restarting" in st:
            crashed.append(c)

        # Parse port mappings like 0.0.0.0:8080->80/tcp
        raw_ports = c.get("ports", "")
        import re
        matches = re.findall(r"(?::)(\d+)->", raw_ports)
        for p in matches:
            if p in ports_mapped:
                collisions.append({
                    "port": p,
                    "container_a": ports_mapped[p],
                    "container_b": c.get("names", c.get("id"))
                })
            else:
                ports_mapped[p] = c.get("names", c.get("id"))

    return {
        "conflicts": collisions,
        "crashed_containers": crashed,
        "total_containers": res.get("count", 0)
    }
