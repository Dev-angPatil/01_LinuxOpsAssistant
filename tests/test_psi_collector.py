"""Unit tests for PSICollector."""

import unittest
from ops_assistant.collectors.psi_collector import PSICollector

class TestPSICollector(unittest.TestCase):
    def setUp(self):
        self.collector = PSICollector()

    def test_collect_returns_metrics(self):
        metrics = self.collector.collect()
        self.assertIsNotNone(metrics)
        self.assertIn(metrics.pressure_level, ["NORMAL", "MODERATE", "CRITICAL", "UNKNOWN"])
        self.assertGreaterEqual(metrics.cpu_some.avg10, 0.0)

if __name__ == "__main__":
    unittest.main()
