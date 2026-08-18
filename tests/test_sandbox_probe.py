"""Unit tests for Ephemeral Sandbox Probe."""

import unittest
from ops_assistant.tools.sandbox_probe import EphemeralSandboxProbe

class TestEphemeralSandboxProbe(unittest.TestCase):
    def setUp(self):
        self.probe = EphemeralSandboxProbe(timeout_seconds=2.0)

    def test_read_only_command_verification(self):
        res = self.probe.verify_command("ps aux | grep nginx")
        self.assertTrue(res.is_verified)
        self.assertEqual(res.exit_code, 0)
        self.assertEqual(res.isolation_mode, "READ_ONLY_INSPECTION")

    def test_valid_syntax_command_verification(self):
        res = self.probe.verify_command("systemctl restart nginx")
        self.assertTrue(res.is_verified)

    def test_invalid_syntax_command(self):
        res = self.probe.verify_command("if [ -f /tmp/test ; then echo err")
        self.assertFalse(res.is_verified)
        self.assertNotEqual(res.exit_code, 0)

if __name__ == "__main__":
    unittest.main()
