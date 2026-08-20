"""Unit tests for Proactive Health Auditor & Recommendation Engine."""

import unittest
from unittest.mock import patch, MagicMock
from ops_assistant.tools import proactive_engine
from ops_assistant.models import (
    SystemHealthSnapshot, CPUMetrics, MemoryMetrics, LoadMetrics, DiskPartition, SystemdUnitState
)


class TestProactiveEngine(unittest.TestCase):
    def test_run_proactive_audit_live(self):
        res = proactive_engine.run_proactive_audit()
        self.assertTrue(res["success"])
        self.assertIn(res["overall_health"], ["OPTIMAL", "WARNING", "CRITICAL"])
        self.assertIsInstance(res["findings"], list)
        self.assertIsInstance(res["findings_count"], int)

    @patch("ops_assistant.collectors.hub.TelemetryHub.get_health_snapshot")
    def test_proactive_audit_critical_scenarios(self, mock_snap):
        mock_snap.return_value = SystemHealthSnapshot(
            timestamp="2026-08-19T18:00:00",
            hostname="test-srv",
            kernel_release="6.8.0-generic",
            uptime_seconds=3600.0,
            cpu=CPUMetrics(user_pct=80.0, zombie_count=5),
            memory=MemoryMetrics(total_mb=8192.0, used_mb=7800.0, free_mb=392.0, available_mb=400.0, used_percent=95.0, swap_total_mb=2048.0, swap_used_mb=1800.0, swap_used_percent=88.0),
            load=LoadMetrics(load_1m=10.5, load_5m=8.2, load_15m=6.1),
            disks=[DiskPartition(mountpoint="/", total_gb=50.0, used_gb=48.0, free_gb=2.0, used_percent=96.0, inodes_percent=90.0)],
            failed_units=[SystemdUnitState(unit_name="nginx.service", load_state="loaded", active_state="failed", sub_state="failed", description="NGINX HTTP Server")],
            pressure_status="CRITICAL"
        )

        res = proactive_engine.run_proactive_audit()
        self.assertTrue(res["success"])
        self.assertEqual(res["overall_health"], "CRITICAL")
        self.assertGreater(res["critical_count"], 0)

        titles = [f["title"] for f in res["findings"]]
        self.assertTrue(any("Kernel Memory/IO Stall" in t for t in titles))
        self.assertTrue(any("Service Failed: nginx.service" in t for t in titles))
        self.assertTrue(any("Disk Partition Full" in t for t in titles))
        self.assertTrue(any("Zombie Processes Detected" in t for t in titles))


if __name__ == "__main__":
    unittest.main()
