"""Unit tests for Dynamic System Causality DAG Engine."""

import unittest
from ops_assistant.explainer.causality_dag import CausalityDAGEngine

class TestCausalityDAGEngine(unittest.TestCase):
    def setUp(self):
        self.engine = CausalityDAGEngine()

    def test_single_event_dag(self):
        logs = ["Out of memory: Killed process 1234 (mysqld)"]
        res = self.engine.build_dag_from_events(logs)
        self.assertEqual(len(res.nodes), 1)
        self.assertTrue(res.nodes[0].is_root_cause)
        self.assertEqual(res.nodes[0].event_type, "KERNEL_OOM")

    def test_multi_event_cascade_dag(self):
        logs = [
            "Out of memory: Killed process 1234 (mysqld)",
            "bind() to 0.0.0.0:80 failed (Address already in use)",
            "502 Bad Gateway: failed to connect to upstream socket"
        ]
        res = self.engine.build_dag_from_events(logs)
        self.assertGreaterEqual(len(res.nodes), 2)
        self.assertGreaterEqual(len(res.root_cause_nodes), 1)
        self.assertIn("graph", res.mermaid_diagram)
        self.assertTrue(any(n.is_root_cause for n in res.nodes))

    def test_empty_logs_fallback(self):
        res = self.engine.build_dag_from_events([])
        self.assertEqual(len(res.nodes), 1)
        self.assertTrue(res.nodes[0].is_root_cause)
        self.assertEqual(res.nodes[0].event_type, "UNKNOWN_ANOMALY")

if __name__ == "__main__":
    unittest.main()
