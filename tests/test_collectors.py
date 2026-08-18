"""Unit tests for Telemetry Collectors."""

import tempfile
import unittest
from pathlib import Path
from ops_assistant.collectors.proc_collector import ProcCollector
from ops_assistant.collectors.journal_collector import JournalCollector
from ops_assistant.collectors.systemd_collector import SystemdCollector
from ops_assistant.collectors.hub import TelemetryHub

class TestCollectors(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mock_proc = Path(self.temp_dir.name)

        # Create mock /proc/meminfo
        meminfo = (
            "MemTotal:       16384000 kB\n"
            "MemFree:         4096000 kB\n"
            "MemAvailable:   12288000 kB\n"
            "Buffers:          512000 kB\n"
            "Cached:          4096000 kB\n"
            "SwapTotal:       2048000 kB\n"
            "SwapFree:        2048000 kB\n"
        )
        (self.mock_proc / "meminfo").write_text(meminfo, encoding="utf-8")

        # Create mock /proc/loadavg
        (self.mock_proc / "loadavg").write_text("0.75 0.50 0.30 2/250 12345\n", encoding="utf-8")

        # Create mock /proc/uptime
        (self.mock_proc / "uptime").write_text("7200.50 14400.00\n", encoding="utf-8")

        # Create mock /proc/stat
        stat = (
            "cpu  1000 50 500 8000 100 20 10 0 0 0\n"
            "cpu0 500 25 250 4000 50 10 5 0 0 0\n"
            "cpu1 500 25 250 4000 50 10 5 0 0 0\n"
        )
        (self.mock_proc / "stat").write_text(stat, encoding="utf-8")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_mock_proc_parsing(self):
        proc = ProcCollector(proc_root=self.mock_proc)
        mem = proc.get_memory_metrics()
        self.assertAlmostEqual(mem.total_mb, 16000.0, delta=100.0)
        self.assertAlmostEqual(mem.available_mb, 12000.0, delta=100.0)
        self.assertGreater(mem.used_percent, 0.0)

        load = proc.get_load_metrics()
        self.assertEqual(load.load_1m, 0.75)
        self.assertEqual(load.load_5m, 0.50)
        self.assertEqual(load.total_processes, 250)

        uptime = proc.get_uptime()
        self.assertEqual(uptime, 7200.50)

    def test_live_proc_collector(self):
        proc = ProcCollector()
        mem = proc.get_memory_metrics()
        self.assertGreater(mem.total_mb, 0)
        self.assertGreaterEqual(mem.swap_used_percent, 0.0)

        cpu = proc.get_cpu_metrics(sample_interval_ms=10)
        self.assertGreaterEqual(cpu.core_count, 1)
        self.assertGreaterEqual(cpu.zombie_count, 0)

        partitions = proc.get_disk_partitions()
        self.assertGreaterEqual(len(partitions), 1)
        self.assertIsNotNone(partitions[0].inodes_total)

    def test_journal_collector(self):
        journal = JournalCollector()
        records = journal.query_journal(unit="systemd", lines=5)
        self.assertIsInstance(records, list)
        self.assertGreater(len(records), 0)

        # Test multi-source query
        all_logs = journal.query_all_relevant_logs(unit="systemd", subsystem="nginx", lines=5)
        self.assertIsInstance(all_logs, list)

    def test_systemd_collector(self):
        sysd = SystemdCollector()
        failed = sysd.get_failed_units()
        self.assertIsInstance(failed, list)

    def test_telemetry_hub(self):
        hub = TelemetryHub()
        snap = hub.get_health_snapshot()
        self.assertIsNotNone(snap.hostname)
        self.assertGreater(snap.uptime_seconds, 0)
        self.assertIsNotNone(snap.pressure_status)

if __name__ == "__main__":
    unittest.main()

