"""Proactive System Health Auditor & Recommendation Engine.

Autonomously assesses real-time system metrics, kernel pressure, disk block & inode usage,
zombie processes, failed systemd units, Docker container states, and security hygiene.
Produces prioritized, actionable recommendations with single-command mitigations.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional
from ops_assistant.collectors.hub import TelemetryHub
from ops_assistant.tools import docker_ops, security_ops, storage_ops, process_ops


class ProactiveHealthAuditor:
    """Runs comprehensive non-invasive health checks and generates proactive guidance."""

    def __init__(self, hub: Optional[TelemetryHub] = None):
        self.hub = hub or TelemetryHub()

    def audit(self) -> Dict[str, Any]:
        """Execute full proactive health audit across all core subsystems."""
        start_t = time.perf_counter()
        findings: List[Dict[str, Any]] = []

        # 1. Telemetry Snapshot & Kernel Pressure
        snap = self.hub.get_health_snapshot()

        if snap.pressure_status == "CRITICAL":
            findings.append({
                "subsystem": "Kernel PSI Pressure",
                "severity": "CRITICAL",
                "title": "Severe Kernel Memory/IO Stall Detected",
                "description": "Kernel PSI reports high CPU/Memory stalls. Immediate OOM or lockup risk.",
                "remediation": "sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches",
                "risk_score": 0.40
            })
        elif snap.pressure_status == "MODERATE":
            findings.append({
                "subsystem": "Kernel PSI Pressure",
                "severity": "WARNING",
                "title": "Moderate Memory/IO Pressure",
                "description": "Active tasks experiencing minor page reclaim delays.",
                "remediation": "ps aux --sort=-%mem | head -n 10",
                "risk_score": 0.05
            })

        # 2. Failed Systemd Units
        if snap.failed_units:
            for u in snap.failed_units:
                findings.append({
                    "subsystem": "Systemd Services",
                    "severity": "CRITICAL",
                    "title": f"Service Failed: {u.unit_name}",
                    "description": f"Unit entered '{u.active_state}/{u.sub_state}': {u.description}",
                    "remediation": f"sudo systemctl restart {u.unit_name}",
                    "risk_score": 0.35
                })

        # 3. Disk & Inode Saturation
        for d in snap.disks:
            if d.used_percent >= 90.0:
                findings.append({
                    "subsystem": "Storage",
                    "severity": "CRITICAL",
                    "title": f"Disk Partition Full: {d.mountpoint} ({d.used_percent}%)",
                    "description": f"Only {d.free_gb:.1f} GB free. File creation and daemon logging will fail.",
                    "remediation": "sudo journalctl --vacuum-size=200M",
                    "risk_score": 0.30
                })
            elif d.used_percent >= 80.0:
                findings.append({
                    "subsystem": "Storage",
                    "severity": "WARNING",
                    "title": f"Disk Partition Near Capacity: {d.mountpoint} ({d.used_percent}%)",
                    "description": f"{d.used_gb:.1f} GB of {d.total_gb:.1f} GB utilized.",
                    "remediation": f"find {d.mountpoint} -xdev -type f -size +100M 2>/dev/null | head -n 10",
                    "risk_score": 0.05
                })

            if d.inodes_percent is not None and d.inodes_percent >= 85.0:
                findings.append({
                    "subsystem": "Storage Inodes",
                    "severity": "CRITICAL",
                    "title": f"Inode Table Exhaustion on {d.mountpoint} ({d.inodes_percent}%)",
                    "description": "Filesystem metadata table nearly exhausted by millions of small files.",
                    "remediation": "sudo find /tmp /var/tmp -xdev -type f -delete 2>/dev/null",
                    "risk_score": 0.70
                })

        # 4. Zombie Defunct Processes
        if snap.cpu.zombie_count > 0:
            findings.append({
                "subsystem": "Process Table",
                "severity": "WARNING",
                "title": f"Zombie Processes Detected ({snap.cpu.zombie_count} defunct)",
                "description": "Exited child processes uncollected by parent PID in kernel table.",
                "remediation": "ps -ef | grep defunct",
                "risk_score": 0.05
            })

        # 5. High Memory / Swap Saturation
        if snap.memory.used_percent >= 90.0 and snap.memory.swap_used_percent >= 70.0:
            findings.append({
                "subsystem": "Memory",
                "severity": "CRITICAL",
                "title": "Severe Physical RAM & Swap Saturation",
                "description": f"RAM {snap.memory.used_percent}% and Swap {snap.memory.swap_used_percent}%. High risk of kernel OOM killer.",
                "remediation": "ps aux --sort=-%mem | head -n 5",
                "risk_score": 0.05
            })

        # 6. Docker Container Health
        try:
            d_conflicts = docker_ops.inspect_container_conflicts()
            if d_conflicts.get("crashed_containers"):
                for c in d_conflicts["crashed_containers"][:3]:
                    findings.append({
                        "subsystem": "Docker",
                        "severity": "WARNING",
                        "title": f"Crashed Docker Container: {c.get('names', c.get('id'))}",
                        "description": f"Status: {c.get('status')}",
                        "remediation": f"docker restart {c.get('id')}",
                        "risk_score": 0.35
                    })
        except Exception:
            pass

        # 7. Security Checks
        try:
            brute = security_ops.detect_ssh_bruteforce(hours=24)
            if brute.get("threat_level") == "HIGH":
                top_ip = brute["top_offending_ips"][0]["ip"] if brute.get("top_offending_ips") else "offender"
                findings.append({
                    "subsystem": "Security / Auth",
                    "severity": "CRITICAL",
                    "title": f"Active SSH Brute-Force Attack ({brute.get('total_failed_attempts')} attempts)",
                    "description": f"Top attacking IP: {top_ip}",
                    "remediation": f"sudo ufw deny from {top_ip}",
                    "risk_score": 0.70
                })
        except Exception:
            pass

        # Sort findings by severity: CRITICAL first, then WARNING, then INFO
        severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        findings.sort(key=lambda x: severity_order.get(x.get("severity", "INFO"), 99))

        overall_health = "CRITICAL" if any(f["severity"] == "CRITICAL" for f in findings) else ("WARNING" if findings else "OPTIMAL")
        elapsed_ms = round((time.perf_counter() - start_t) * 1000.0, 2)

        return {
            "success": True,
            "overall_health": overall_health,
            "findings_count": len(findings),
            "critical_count": sum(1 for f in findings if f["severity"] == "CRITICAL"),
            "warning_count": sum(1 for f in findings if f["severity"] == "WARNING"),
            "findings": findings,
            "latency_ms": elapsed_ms,
            "system_snapshot": snap.to_dict()
        }


def run_proactive_audit() -> Dict[str, Any]:
    """Convenience function to run proactive system audit."""
    auditor = ProactiveHealthAuditor()
    return auditor.audit()
