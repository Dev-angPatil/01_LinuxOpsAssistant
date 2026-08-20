"""Security, SSH Configuration, Brute-Force & SUID Audit Tools.

Audits open listening ports vs security policies, SSH daemon hardening flags,
auth log brute-force attempts, and anomalous SUID/SGID executable permissions.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
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


def inspect_ssh_security(sshd_config_path: str = "/etc/ssh/sshd_config") -> Dict[str, Any]:
    """Audit SSH daemon configuration for common hardening settings."""
    findings = []
    recommendations = []
    parsed_directives = {}

    p = Path(sshd_config_path)
    if not p.exists():
        return {
            "success": False,
            "error": f"SSH configuration file not found at {sshd_config_path}",
            "findings": [],
            "security_score": 0.0
        }

    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        parsed_directives[parts[0].lower()] = parts[1].strip()
    except Exception as e:
        return {"success": False, "error": str(e), "findings": [], "security_score": 0.0}

    # 1. PermitRootLogin
    permit_root = parsed_directives.get("permitrootlogin", "yes").lower()
    if permit_root in ("no", "prohibit-password", "without-password"):
        findings.append({"check": "PermitRootLogin", "status": "SECURE", "value": permit_root})
    else:
        findings.append({"check": "PermitRootLogin", "status": "RISK", "value": permit_root})
        recommendations.append("Set 'PermitRootLogin no' or 'prohibit-password' to prevent direct root access.")

    # 2. PasswordAuthentication
    pass_auth = parsed_directives.get("passwordauthentication", "yes").lower()
    if pass_auth == "no":
        findings.append({"check": "PasswordAuthentication", "status": "SECURE", "value": pass_auth})
    else:
        findings.append({"check": "PasswordAuthentication", "status": "WARNING", "value": pass_auth})
        recommendations.append("Consider disabling PasswordAuthentication in favor of public key authentication.")

    # 3. Port
    port = parsed_directives.get("port", "22")
    findings.append({"check": "SSH Port", "status": "INFO", "value": port})

    # 4. X11Forwarding
    x11 = parsed_directives.get("x11forwarding", "no").lower()
    if x11 == "no":
        findings.append({"check": "X11Forwarding", "status": "SECURE", "value": x11})
    else:
        findings.append({"check": "X11Forwarding", "status": "WARNING", "value": x11})

    # 5. MaxAuthTries
    max_tries = parsed_directives.get("maxauthtries", "6")
    try:
        if int(max_tries) <= 4:
            findings.append({"check": "MaxAuthTries", "status": "SECURE", "value": max_tries})
        else:
            findings.append({"check": "MaxAuthTries", "status": "WARNING", "value": max_tries})
            recommendations.append("Lower MaxAuthTries to 3 or 4 to mitigate brute-force attempts.")
    except ValueError:
        pass

    checkable = [f for f in findings if f.get("status") in ("SECURE", "WARNING", "RISK")]
    secure_count = sum(1 for f in checkable if f.get("status") == "SECURE")
    total_checks = max(1, len(checkable))
    score = round((secure_count / total_checks) * 100.0, 1)

    return {
        "success": True,
        "config_path": str(p),
        "security_score": score,
        "findings": findings,
        "recommendations": recommendations,
        "directives": parsed_directives
    }


def detect_ssh_bruteforce(hours: int = 24) -> Dict[str, Any]:
    """Scan system auth logs and journal for failed SSH authentication attempts."""
    failed_ips: Dict[str, int] = {}
    failed_users: Dict[str, int] = {}
    total_failed = 0

    log_sources = ["/var/log/auth.log", "/var/log/secure"]
    scanned_lines = 0

    for log_path in log_sources:
        if os.path.exists(log_path):
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        scanned_lines += 1
                        if "Failed password" in line or "authentication failure" in line:
                            total_failed += 1
                            ip_match = re.search(r"from\s+(\d+\.\d+\.\d+\.\d+)", line)
                            user_match = re.search(r"for\s+(?:invalid user\s+)?(\S+)", line)
                            if ip_match:
                                ip = ip_match.group(1)
                                failed_ips[ip] = failed_ips.get(ip, 0) + 1
                            if user_match:
                                u = user_match.group(1)
                                failed_users[u] = failed_users.get(u, 0) + 1
            except Exception:
                pass

    if scanned_lines == 0 and shutil.which("journalctl"):
        rc, stdout, _ = _run_cmd(["journalctl", "-u", "ssh", "-u", "sshd", f"--since={hours}h ago", "--no-pager", "-n", "500"])
        if rc == 0:
            for line in stdout.splitlines():
                scanned_lines += 1
                if "Failed password" in line:
                    total_failed += 1
                    ip_match = re.search(r"from\s+(\d+\.\d+\.\d+\.\d+)", line)
                    user_match = re.search(r"for\s+(?:invalid user\s+)?(\S+)", line)
                    if ip_match:
                        ip = ip_match.group(1)
                        failed_ips[ip] = failed_ips.get(ip, 0) + 1
                    if user_match:
                        u = user_match.group(1)
                        failed_users[u] = failed_users.get(u, 0) + 1

    top_ips = sorted(failed_ips.items(), key=lambda x: x[1], reverse=True)[:10]
    top_users = sorted(failed_users.items(), key=lambda x: x[1], reverse=True)[:10]

    threat_level = "HIGH" if total_failed > 50 else ("ELEVATED" if total_failed > 10 else "NORMAL")

    return {
        "success": True,
        "scanned_lines": scanned_lines,
        "total_failed_attempts": total_failed,
        "threat_level": threat_level,
        "top_offending_ips": [{"ip": ip, "attempts": count} for ip, count in top_ips],
        "targeted_usernames": [{"user": u, "attempts": count} for u, count in top_users],
        "recommendation": "Use UFW or fail2ban to automatically jail recurring offending IPs." if total_failed > 10 else "No active SSH brute force attacks detected."
    }


def audit_suid_binaries() -> Dict[str, Any]:
    """Audit system binaries for SUID/SGID permission bits."""
    standard_suid = {
        "/usr/bin/sudo", "/usr/bin/passwd", "/usr/bin/su", "/usr/bin/pkexec",
        "/usr/bin/gpasswd", "/usr/bin/newgrp", "/usr/bin/chfn", "/usr/bin/chsh",
        "/usr/lib/openssh/ssh-keysign", "/usr/bin/mount", "/usr/bin/umount",
        "/usr/bin/ping", "/usr/bin/fusermount", "/usr/bin/fusermount3"
    }

    found_suid = []
    anomalies = []

    search_dirs = ["/bin", "/sbin", "/usr/bin", "/usr/sbin", "/usr/local/bin"]
    seen_dirs = set()
    seen_paths = set()
    for sdir in search_dirs:
        if os.path.exists(sdir):
            real_dir = os.path.realpath(sdir)
            if real_dir in seen_dirs:
                continue
            seen_dirs.add(real_dir)
            try:
                for entry in os.listdir(sdir):
                    full_p = os.path.join(sdir, entry)
                    real_p = os.path.realpath(full_p)
                    if real_p in seen_paths:
                        continue
                    seen_paths.add(real_p)
                    try:
                        st = os.stat(full_p, follow_symlinks=False)
                        if st.st_mode & 0o4000 or st.st_mode & 0o2000:
                            found_suid.append(full_p)
                            if full_p not in standard_suid and real_p not in standard_suid:
                                anomalies.append(full_p)
                    except (OSError, PermissionError):
                        pass
            except Exception:
                pass

    return {
        "success": True,
        "total_suid_count": len(found_suid),
        "anomalous_suid_count": len(anomalies),
        "anomalous_binaries": anomalies[:20],
        "all_suid_binaries": found_suid[:50],
        "status": "ATTENTION_REQUIRED" if anomalies else "CLEAN"
    }


def audit_security() -> Dict[str, Any]:
    """Consolidated system security audit combining ports, SSH, brute-force, and SUID checks."""
    from ops_assistant.tools.network_ops import list_listening_ports, get_firewall_status

    ports = list_listening_ports()
    fw = get_firewall_status()
    ssh = inspect_ssh_security()
    brute = detect_ssh_bruteforce(hours=24)
    suid = audit_suid_binaries()

    overall_status = "HEALTHY"
    if brute.get("threat_level") == "HIGH" or suid.get("anomalous_suid_count", 0) > 3 or ssh.get("security_score", 100) < 50:
        overall_status = "CRITICAL"
    elif brute.get("threat_level") == "ELEVATED" or ssh.get("security_score", 100) < 75 or fw.get("status") == "inactive":
        overall_status = "WARNING"

    return {
        "success": True,
        "overall_status": overall_status,
        "firewall": fw,
        "listening_ports_count": len(ports),
        "ssh_audit": ssh,
        "brute_force_audit": brute,
        "suid_audit": suid
    }
