"""Unit tests for Safety Validator and Executor."""

import unittest
from ops_assistant.tools.safety import CommandSafetyValidator
from ops_assistant.tools.executor import SafeExecutor
from ops_assistant.models import SafetyLevel

class TestSafetyAndExecutor(unittest.TestCase):
    def setUp(self):
        self.validator = CommandSafetyValidator()
        self.executor = SafeExecutor()

    def test_read_only_commands(self):
        cmds = [
            "cat /etc/os-release",
            "journalctl -u nginx -n 50 --no-pager",
            "free -h",
            "df -h /",
            "systemctl status sshd"
        ]
        for cmd in cmds:
            lvl, score, _ = self.validator.evaluate_safety(cmd)
            self.assertEqual(lvl, SafetyLevel.READ_ONLY, f"Expected READ_ONLY for {cmd}")
            self.assertLessEqual(score, 0.2)

    def test_modifying_commands(self):
        cmds = [
            "sudo systemctl restart nginx",
            "systemctl reload apache2",
            "touch /tmp/test.txt"
        ]
        for cmd in cmds:
            lvl, score, _ = self.validator.evaluate_safety(cmd)
            self.assertEqual(lvl, SafetyLevel.MODIFYING, f"Expected MODIFYING for {cmd}")

    def test_high_risk_and_destructive(self):
        lvl, score, _ = self.validator.evaluate_safety("sudo rm -rf /")
        self.assertEqual(lvl, SafetyLevel.DESTRUCTIVE)
        self.assertEqual(score, 1.0)

        lvl2, _, _ = self.validator.evaluate_safety("mkfs.ext4 /dev/sda1")
        self.assertEqual(lvl2, SafetyLevel.DESTRUCTIVE)

        lvl3, _, _ = self.validator.evaluate_safety("kill -9 12345")
        self.assertEqual(lvl3, SafetyLevel.HIGH_RISK)

        lvl4, _, _ = self.validator.evaluate_safety(":(){ :|:& };:")
        self.assertEqual(lvl4, SafetyLevel.DESTRUCTIVE)

        lvl5, _, _ = self.validator.evaluate_safety("echo 'root::0:0' > /etc/passwd")
        self.assertEqual(lvl5, SafetyLevel.DESTRUCTIVE)

    def test_executor_blocks_destructive(self):
        res = self.executor.execute("sudo rm -rf /", allow_destructive=False)
        self.assertFalse(res["executed"])
        self.assertIn("BLOCKED", res["stderr"])

    def test_executor_dry_run(self):
        res = self.executor.execute("sudo systemctl restart nginx", dry_run=True)
        self.assertFalse(res["executed"])
        self.assertTrue(res["dry_run"])
        self.assertIn("[DRY_RUN PREVIEW]", res["stdout"])

    def test_executor_safe_read(self):
        res = self.executor.execute("echo 'test-ops-assistant'")
        self.assertTrue(res["executed"])
        self.assertEqual(res["returncode"], 0)
        self.assertIn("test-ops-assistant", res["stdout"])

    def test_executor_rollback(self):
        self.executor.execute("echo 'hello'", rollback_cmd="echo 'rollback'")
        rb_res = self.executor.rollback_last()
        self.assertTrue(rb_res["executed"])
        self.assertEqual(rb_res["command"], "echo 'rollback'")

if __name__ == "__main__":
    unittest.main()

