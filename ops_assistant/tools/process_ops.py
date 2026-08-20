"""
Process and Service Operations — list, kill, inspect processes and
start/stop/restart/enable/disable systemd services.
"""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: List[str], timeout: int = 10) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out after {timeout}s"


# ---------------------------------------------------------------------------
# Process operations
# ---------------------------------------------------------------------------

def list_processes(sort_by: str = "cpu", top_n: int = 20) -> Dict[str, Any]:
    """
    Return the top *top_n* processes sorted by CPU or memory.

    Returns:
        {
          "processes": [{"pid": int, "user": str, "cpu": float, "mem": float,
                         "vsz": str, "rss": str, "stat": str, "command": str}],
          "sort_by": str,
          "error": str | None
        }
    """
    sort_flag = "--sort=-%cpu" if sort_by.lower() in ("cpu", "c") else "--sort=-%mem"
    cmd = [
        "ps", "axo", "pid,user,%cpu,%mem,vsz,rss,stat,comm",
        sort_flag,
        "--no-headers",
    ]
    rc, stdout, stderr = _run(cmd)
    if rc != 0:
        return {"processes": [], "sort_by": sort_by, "error": stderr}

    processes: List[Dict[str, Any]] = []
    for line in stdout.strip().splitlines()[:top_n]:
        parts = line.split(None, 7)
        if len(parts) >= 8:
            try:
                processes.append({
                    "pid": int(parts[0]),
                    "user": parts[1],
                    "cpu": float(parts[2]),
                    "mem": float(parts[3]),
                    "vsz": parts[4],
                    "rss": parts[5],
                    "stat": parts[6],
                    "command": parts[7],
                })
            except (ValueError, IndexError):
                pass

    return {"processes": processes, "sort_by": sort_by, "error": None}


def kill_process(
    pid: Optional[int] = None,
    name: Optional[str] = None,
    signal: str = "TERM",
) -> Dict[str, Any]:
    """
    Send *signal* to the process identified by *pid* or *name*.

    Returns:
        {"success": bool, "command": str, "stdout": str, "stderr": str}
    """
    if pid is not None:
        cmd = ["kill", f"-{signal.upper()}", str(pid)]
    elif name:
        cmd = ["pkill", f"-{signal.upper()}", name]
    else:
        return {"success": False, "command": "", "stdout": "", "stderr": "No pid or name provided."}

    rc, stdout, stderr = _run(cmd)
    return {
        "success": rc == 0,
        "command": " ".join(cmd),
        "stdout": stdout,
        "stderr": stderr,
        "returncode": rc,
    }


def get_process_info(pid: int) -> Dict[str, Any]:
    """Return detailed info about a single process by PID."""
    rc, stdout, stderr = _run(
        ["ps", "-p", str(pid), "-o", "pid,ppid,user,%cpu,%mem,vsz,rss,stat,etime,comm,args",
         "--no-headers"]
    )
    if rc != 0 or not stdout.strip():
        return {"error": f"Process {pid} not found or access denied.", "pid": pid}

    parts = stdout.strip().split(None, 10)
    if len(parts) < 10:
        return {"error": "Could not parse process info.", "raw": stdout, "pid": pid}

    return {
        "pid": int(parts[0]),
        "ppid": int(parts[1]),
        "user": parts[2],
        "cpu": float(parts[3]),
        "mem": float(parts[4]),
        "vsz": parts[5],
        "rss": parts[6],
        "stat": parts[7],
        "elapsed": parts[8],
        "command": parts[9],
        "args": parts[10] if len(parts) > 10 else parts[9],
    }


# ---------------------------------------------------------------------------
# Service operations (systemd-first; graceful fallback messages)
# ---------------------------------------------------------------------------

def _systemctl(subcmd: str, service: str, timeout: int = 15) -> Dict[str, Any]:
    """Run a systemctl command and return structured result."""
    cmd = ["systemctl", subcmd, service]
    rc, stdout, stderr = _run(cmd, timeout=timeout)
    return {
        "success": rc == 0,
        "command": " ".join(cmd),
        "stdout": stdout,
        "stderr": stderr,
        "returncode": rc,
    }


def show_service_status(service: str) -> Dict[str, Any]:
    """Return rich status info for a systemd service."""
    # Primary: systemctl status
    rc, stdout, stderr = _run(
        ["systemctl", "status", service, "--no-pager", "-l"], timeout=10
    )
    # Also grab active state quickly via show
    rc2, show_out, _ = _run(
        ["systemctl", "show", service,
         "--property=ActiveState,SubState,LoadState,MainPID,ExecMainStartTimestamp,Description"],
        timeout=5,
    )
    props: Dict[str, str] = {}
    for line in show_out.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()

    return {
        "service": service,
        "active_state": props.get("ActiveState", "unknown"),
        "sub_state": props.get("SubState", "unknown"),
        "load_state": props.get("LoadState", "unknown"),
        "main_pid": props.get("MainPID", ""),
        "started": props.get("ExecMainStartTimestamp", ""),
        "description": props.get("Description", ""),
        "status_output": stdout,
        "success": rc == 0 or rc2 == 0,
        "error": stderr if rc != 0 else None,
    }


def start_service(service: str) -> Dict[str, Any]:
    return _systemctl("start", service)


def stop_service(service: str) -> Dict[str, Any]:
    return _systemctl("stop", service)


def restart_service(service: str) -> Dict[str, Any]:
    return _systemctl("restart", service)


def reload_service(service: str) -> Dict[str, Any]:
    return _systemctl("reload-or-restart", service)


def enable_service(service: str) -> Dict[str, Any]:
    return _systemctl("enable", service)


def disable_service(service: str) -> Dict[str, Any]:
    return _systemctl("disable", service)
