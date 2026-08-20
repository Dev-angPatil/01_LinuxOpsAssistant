"""
Log Operations — tail logs, surface error-level messages, and query the
kernel ring buffer (dmesg) for the Linux Ops Assistant.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _run(cmd: List[str], timeout: int = 10) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out after {timeout}s"


def _has_journalctl() -> bool:
    rc, _, _ = _run(["which", "journalctl"])
    return rc == 0


# ---------------------------------------------------------------------------
# Log tailing
# ---------------------------------------------------------------------------

def tail_log(
    service_or_path: str,
    lines: int = 50,
) -> Dict[str, Any]:
    """
    Tail logs for a systemd service name or a direct file path.

    Returns:
        {"source": str, "lines": list[str], "error": str | None}
    """
    # If it looks like a file path, tail it directly
    candidate = Path(os.path.expanduser(service_or_path))
    if candidate.is_file():
        rc, stdout, stderr = _run(["tail", f"-n{lines}", str(candidate)])
        return {
            "source": str(candidate),
            "type": "file",
            "lines": stdout.splitlines(),
            "error": stderr if rc != 0 else None,
        }

    # Otherwise treat as systemd unit name
    if _has_journalctl():
        # Strip .service suffix if provided for normalisation
        unit = service_or_path.removesuffix(".service")
        cmd = ["journalctl", "-u", unit, "-n", str(lines), "--no-pager", "-o", "short-iso"]
        rc, stdout, stderr = _run(cmd, timeout=15)
        if rc == 0 and stdout.strip():
            return {
                "source": unit,
                "type": "journald",
                "lines": stdout.splitlines(),
                "error": None,
            }

    # Fallback: scan /var/log for a matching file
    log_dir = Path("/var/log")
    candidates = list(log_dir.glob(f"{service_or_path}*")) + list(log_dir.glob(f"*{service_or_path}*"))
    for log_file in candidates:
        if log_file.is_file():
            rc, stdout, stderr = _run(["tail", f"-n{lines}", str(log_file)])
            return {
                "source": str(log_file),
                "type": "file",
                "lines": stdout.splitlines(),
                "error": stderr if rc != 0 else None,
            }

    return {
        "source": service_or_path,
        "type": "unknown",
        "lines": [],
        "error": f"Could not find logs for '{service_or_path}'",
    }


# ---------------------------------------------------------------------------
# Error surfacing
# ---------------------------------------------------------------------------

def show_errors(since: str = "1h") -> Dict[str, Any]:
    """
    Return error and critical priority log lines from journald since *since*
    (e.g. "1h", "30min", "2023-01-01").

    Falls back to scanning /var/log/syslog or /var/log/messages.
    """
    if _has_journalctl():
        cmd = [
            "journalctl",
            "-p", "err",          # error and above (crit, alert, emerg)
            "--since", f"-{since}",
            "--no-pager",
            "-o", "short-iso",
            "-n", "100",
        ]
        rc, stdout, stderr = _run(cmd, timeout=15)
        if rc == 0:
            lines = stdout.splitlines()
            return {
                "source": "journald",
                "since": since,
                "count": len([l for l in lines if l.strip() and not l.startswith("--")]),
                "lines": lines,
                "error": None,
            }

    # Fallback: grep syslog / messages for ERROR/CRIT
    for log_file in ["/var/log/syslog", "/var/log/messages"]:
        if Path(log_file).is_file():
            rc, stdout, stderr = _run(
                ["grep", "-Ei", r"(error|critical|fail|panic|oom)", log_file],
                timeout=10,
            )
            if rc == 0:
                tail = stdout.splitlines()[-100:]
                return {
                    "source": log_file,
                    "since": "full file (grep fallback)",
                    "count": len(tail),
                    "lines": tail,
                    "error": None,
                }

    return {
        "source": "none",
        "since": since,
        "count": 0,
        "lines": [],
        "error": "No log source available (journald not found, /var/log/syslog absent)",
    }


# ---------------------------------------------------------------------------
# Kernel ring buffer
# ---------------------------------------------------------------------------

def show_kernel_errors(lines: int = 50) -> Dict[str, Any]:
    """
    Return recent kernel messages from dmesg, filtered for errors/warnings.
    """
    rc, stdout, stderr = _run(
        ["dmesg", "-T", "--level=err,warn,crit,emerg", "-x"],
        timeout=10,
    )
    if rc != 0:
        # Some systems don't support --level; try without
        rc, stdout, stderr = _run(["dmesg", "-T"], timeout=10)

    log_lines = stdout.splitlines()[-lines:]
    return {
        "source": "dmesg",
        "count": len(log_lines),
        "lines": log_lines,
        "error": stderr if rc != 0 else None,
    }


# ---------------------------------------------------------------------------
# Cron listing
# ---------------------------------------------------------------------------

def list_cron_jobs() -> Dict[str, Any]:
    """List the current user's crontab and any system-wide cron jobs."""
    result: Dict[str, Any] = {"user_crontab": [], "system_cron": [], "error": None}

    # User crontab
    rc, stdout, stderr = _run(["crontab", "-l"])
    if rc == 0:
        result["user_crontab"] = [l for l in stdout.splitlines() if l.strip() and not l.startswith("#")]
    elif "no crontab" in stderr.lower():
        result["user_crontab"] = []
    else:
        result["error"] = stderr

    # System cron.d
    cron_dirs = ["/etc/cron.d", "/etc/cron.daily", "/etc/cron.hourly",
                 "/etc/cron.weekly", "/etc/cron.monthly"]
    for d in cron_dirs:
        p = Path(d)
        if p.is_dir():
            for f in p.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    result["system_cron"].append({"dir": d, "file": f.name})

    return result


# ---------------------------------------------------------------------------
# User listing
# ---------------------------------------------------------------------------

def who_is_logged_in() -> Dict[str, Any]:
    """Return currently logged-in users."""
    rc, stdout, stderr = _run(["who"])
    sessions: List[Dict[str, str]] = []
    for line in stdout.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            sessions.append({
                "user": parts[0],
                "tty": parts[1],
                "login_time": " ".join(parts[2:4]) if len(parts) >= 4 else "",
                "from": parts[4].strip("()") if len(parts) >= 5 else "",
            })
    return {"sessions": sessions, "raw": stdout, "error": stderr if rc != 0 else None}


def list_all_users() -> Dict[str, Any]:
    """Return all system users from /etc/passwd."""
    users: List[Dict[str, str]] = []
    try:
        with open("/etc/passwd") as fh:
            for line in fh:
                parts = line.strip().split(":")
                if len(parts) >= 7:
                    users.append({
                        "username": parts[0],
                        "uid": parts[2],
                        "gid": parts[3],
                        "comment": parts[4],
                        "home": parts[5],
                        "shell": parts[6],
                    })
    except OSError as e:
        return {"users": [], "error": str(e)}
    return {"users": users, "error": None}
