"""
System Maintenance, Crontab Automation & Boot Performance Ops.

Provides safe crontab management, systemd journal vacuuming,
SSD TRIM orchestration, boot time bottleneck analysis, and distro package cache cleanup.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Tuple


def _run_cmd(cmd: List[str], timeout: int = 15) -> Tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout}s"
    except Exception as e:
        return 1, "", str(e)


def list_cron_jobs() -> Dict[str, Any]:
    """List user and system cron jobs."""
    user_jobs = []
    rc, stdout, _ = _run_cmd(["crontab", "-l"])
    if rc == 0:
        for line in stdout.strip().splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                user_jobs.append(line)

    system_cron_dirs = ["/etc/cron.d", "/etc/cron.daily", "/etc/cron.hourly", "/etc/cron.weekly", "/etc/cron.monthly"]
    system_jobs = []
    for cd in system_cron_dirs:
        if os.path.exists(cd):
            try:
                for entry in os.listdir(cd):
                    full_p = os.path.join(cd, entry)
                    if os.path.isfile(full_p):
                        system_jobs.append(f"{cd}/{entry}")
            except Exception:
                pass

    return {
        "success": True,
        "user_crontab_jobs": user_jobs,
        "user_jobs_count": len(user_jobs),
        "system_cron_files": system_jobs,
        "system_files_count": len(system_jobs)
    }


def add_cron_job(schedule: str, command: str) -> Dict[str, Any]:
    """Add a new cron job entry for current user after validating schedule syntax."""
    schedule = schedule.strip()
    command = command.strip()

    # Basic 5-part cron schedule syntax check
    parts = schedule.split()
    if len(parts) != 5:
        return {
            "success": False,
            "error": f"Invalid cron schedule format '{schedule}'. Must contain exactly 5 fields (e.g. '0 2 * * *')."
        }

    rc, stdout, _ = _run_cmd(["crontab", "-l"])
    existing = stdout if rc == 0 else ""
    new_entry = f"{schedule} {command}"

    if new_entry in existing:
        return {
            "success": True,
            "message": "Cron job already exists in user crontab.",
            "entry": new_entry
        }

    updated = (existing.rstrip() + "\n" + new_entry + "\n").lstrip()

    try:
        p = subprocess.run(["crontab", "-"], input=updated, text=True, capture_output=True, timeout=5)
        if p.returncode == 0:
            return {
                "success": True,
                "entry": new_entry,
                "message": f"Successfully added cron job: {new_entry}",
                "rollback_command": f"# Remove entry '{new_entry}' via crontab"
            }
        else:
            return {"success": False, "error": p.stderr}
    except Exception as e:
        return {"success": False, "error": str(e)}


def remove_cron_job(pattern: str) -> Dict[str, Any]:
    """Remove cron jobs matching a pattern from user crontab."""
    rc, stdout, _ = _run_cmd(["crontab", "-l"])
    if rc != 0 or not stdout.strip():
        return {"success": False, "error": "No user crontab found."}

    lines = stdout.splitlines()
    remaining = []
    removed = []

    for line in lines:
        if pattern in line:
            removed.append(line)
        else:
            remaining.append(line)

    if not removed:
        return {"success": False, "message": f"No cron jobs matched pattern '{pattern}'."}

    updated = "\n".join(remaining) + ("\n" if remaining else "")
    try:
        p = subprocess.run(["crontab", "-"], input=updated, text=True, capture_output=True, timeout=5)
        return {
            "success": p.returncode == 0,
            "removed_jobs": removed,
            "removed_count": len(removed),
            "message": f"Successfully removed {len(removed)} cron job(s)." if p.returncode == 0 else p.stderr
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


def vacuum_journal(max_size: str = "200M", dry_run: bool = True) -> Dict[str, Any]:
    """Vacuum systemd journal logs to reclaim storage space."""
    if not shutil.which("journalctl"):
        return {"success": False, "error": "journalctl not available on this system."}

    rc, stdout, _ = _run_cmd(["journalctl", "--disk-usage"])
    usage_info = stdout.strip() if rc == 0 else "Unknown"

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "current_journal_usage": usage_info,
            "proposed_command": f"sudo journalctl --vacuum-size={max_size}",
            "message": f"Simulated journal vacuum to {max_size}. Current usage: {usage_info}"
        }

    rc, stdout, stderr = _run_cmd(["journalctl", f"--vacuum-size={max_size}"])
    return {
        "success": rc == 0,
        "dry_run": False,
        "output": stdout.strip(),
        "message": f"Journal vacuum completed: {stdout.strip()}" if rc == 0 else stderr,
        "error": stderr if rc != 0 else None
    }


def trim_ssds(dry_run: bool = True) -> Dict[str, Any]:
    """Issue fstrim across all mounted filesystems."""
    if not shutil.which("fstrim"):
        return {"success": False, "error": "fstrim utility not found."}

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "proposed_command": "sudo fstrim -av",
            "message": "Simulated SSD TRIM operation. Run without dry_run to trim mounted block devices."
        }

    rc, stdout, stderr = _run_cmd(["fstrim", "-av"])
    return {
        "success": rc == 0,
        "dry_run": False,
        "output": stdout.strip(),
        "message": stdout.strip() if rc == 0 else stderr,
        "error": stderr if rc != 0 else None
    }


def analyze_boot_time() -> Dict[str, Any]:
    """Analyze Linux startup bottlenecks using systemd-analyze."""
    if not shutil.which("systemd-analyze"):
        return {"success": False, "error": "systemd-analyze is not available on this system."}

    rc_time, stdout_time, _ = _run_cmd(["systemd-analyze", "time"])
    overall_time = stdout_time.strip() if rc_time == 0 else "Unknown"

    rc_blame, stdout_blame, _ = _run_cmd(["systemd-analyze", "blame"])
    blame_items = []
    if rc_blame == 0:
        for line in stdout_blame.strip().splitlines()[:15]:
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                blame_items.append({"duration": parts[0], "service": parts[1]})

    return {
        "success": True,
        "overall_boot_time": overall_time,
        "top_slow_services": blame_items,
        "count": len(blame_items)
    }


def clean_package_cache(dry_run: bool = True) -> Dict[str, Any]:
    """Clean package manager downloaded cache files across Debian/Ubuntu, RHEL, Arch, and Alpine."""
    pkg_mgr = None
    clean_cmd = []

    if shutil.which("apt-get"):
        pkg_mgr = "apt"
        clean_cmd = ["apt-get", "clean"]
    elif shutil.which("dnf"):
        pkg_mgr = "dnf"
        clean_cmd = ["dnf", "clean", "all"]
    elif shutil.which("pacman"):
        pkg_mgr = "pacman"
        clean_cmd = ["pacman", "-Sc", "--noconfirm"]
    elif shutil.which("apk"):
        pkg_mgr = "apk"
        clean_cmd = ["apk", "cache", "clean"]

    if not pkg_mgr:
        return {"success": False, "error": "No supported package manager found (apt/dnf/pacman/apk)."}

    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "package_manager": pkg_mgr,
            "proposed_command": "sudo " + " ".join(clean_cmd),
            "message": f"Simulated {pkg_mgr} cache purge. Run with dry_run=False to delete package archives."
        }

    rc, stdout, stderr = _run_cmd(clean_cmd)
    return {
        "success": rc == 0,
        "dry_run": False,
        "package_manager": pkg_mgr,
        "output": stdout.strip(),
        "message": f"Successfully cleaned {pkg_mgr} cache." if rc == 0 else stderr,
        "error": stderr if rc != 0 else None
    }
