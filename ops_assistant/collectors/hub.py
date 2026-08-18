"""Telemetry Hub for consolidated Linux health diagnostics."""

import os
import platform
from datetime import datetime, timezone
from dataclasses import asdict
from ops_assistant.models import SystemHealthSnapshot
from ops_assistant.collectors.proc_collector import ProcCollector
from ops_assistant.collectors.journal_collector import JournalCollector
from ops_assistant.collectors.systemd_collector import SystemdCollector
from ops_assistant.collectors.psi_collector import PSICollector

class TelemetryHub:
    def __init__(self):
        self.proc = ProcCollector()
        self.journal = JournalCollector()
        self.systemd = SystemdCollector()
        self.psi = PSICollector()

    def get_health_snapshot(self) -> SystemHealthSnapshot:
        mem = self.proc.get_memory_metrics()
        cpu = self.proc.get_cpu_metrics(sample_interval_ms=30)
        load = self.proc.get_load_metrics()
        disks = self.proc.get_disk_partitions()
        failed = self.systemd.get_failed_units()
        uptime = self.proc.get_uptime()
        psi_data = self.psi.collect()

        # Determine overall pressure status
        pressure = "NORMAL"
        if psi_data.is_available and psi_data.pressure_level in ["MODERATE", "CRITICAL"]:
            pressure = f"PSI_{psi_data.pressure_level}_STALL"
        elif mem.used_percent > 90.0:
            pressure = "MEMORY_PRESSURE"
        elif mem.swap_used_percent > 80.0:
            pressure = "SWAP_PRESSURE"
        elif load.load_1m > cpu.core_count * 2.0:
            pressure = "CPU_SATURATION"
        elif cpu.iowait_pct > 30.0:
            pressure = "IOWAIT_SATURATION"
        elif cpu.zombie_count > 5:
            pressure = f"ZOMBIE_ACCUMULATION ({cpu.zombie_count})"
        elif any(d.used_percent > 90.0 for d in disks):
            pressure = "DISK_FULL"
        elif any(d.inodes_percent and d.inodes_percent > 90.0 for d in disks):
            pressure = "INODES_EXHAUSTED"
        elif len(failed) > 0:
            pressure = f"FAILED_UNITS_DETECTED ({len(failed)})"

        return SystemHealthSnapshot(
            timestamp=datetime.now(timezone.utc).isoformat(),
            hostname=platform.node() or "localhost",
            kernel_release=platform.release() or "Linux",
            uptime_seconds=round(uptime, 1),
            cpu=cpu,
            memory=mem,
            load=load,
            disks=disks,
            failed_units=failed,
            pressure_status=pressure,
            psi_metrics=asdict(psi_data) if psi_data.is_available else None
        )
