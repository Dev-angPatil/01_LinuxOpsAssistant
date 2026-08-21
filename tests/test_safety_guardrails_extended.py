import unittest
from ops_assistant.tools.safety import CommandSafetyValidator
from ops_assistant.models import SafetyLevel


class TestSafetyGuardrailsExtended(unittest.TestCase):
    def setUp(self):
        self.validator = CommandSafetyValidator()

    def test_catastrophic_rm_blocked(self):
        dangerous_cmds = [
            "rm -rf /",
            "rm -rf /*",
            "rm -rf /etc",
            "rm -rf /var",
            "rm -rf /usr",
            "rm -rf ~",
            "rm -rf $HOME",
            "rm -f /etc/passwd",
            "rm -f /etc/shadow",
            "rm -f /etc/sudoers",
        ]
        for cmd in dangerous_cmds:
            lvl, score, reason = self.validator.evaluate_safety(cmd)
            self.assertEqual(lvl, SafetyLevel.DESTRUCTIVE, f"Failed to block: {cmd}")
            self.assertTrue(self.validator.is_destructive(cmd))

    def test_disk_formatting_and_raw_writes_blocked(self):
        raw_writes = [
            "mkfs.ext4 /dev/sda1",
            "mkfs.xfs /dev/nvme0n1p1",
            "wipefs -a /dev/sdb",
            "dd if=/dev/zero of=/dev/sda bs=1M",
            "echo 1 > /proc/sysrq-trigger",
            "cat /dev/null > /etc/passwd",
        ]
        for cmd in raw_writes:
            lvl, score, reason = self.validator.evaluate_safety(cmd)
            self.assertEqual(lvl, SafetyLevel.DESTRUCTIVE, f"Failed to block raw write: {cmd}")

    def test_obfuscation_decoding_blocked(self):
        # Hex encoded rm -rf /
        hex_cmd = r"echo -e '\x72\x6d\x20\x2d\x72\x66\x20\x2f' | bash"
        lvl, score, reason = self.validator.evaluate_safety(hex_cmd)
        self.assertEqual(lvl, SafetyLevel.DESTRUCTIVE)

        # Base64 encoded rm -rf /
        b64_cmd = "echo 'cm0gLXJmIC8=' | base64 -d | sh"
        lvl, score, reason = self.validator.evaluate_safety(b64_cmd)
        self.assertEqual(lvl, SafetyLevel.DESTRUCTIVE)

    def test_fork_bomb_blocked(self):
        fork_bombs = [
            ":(){ :|:& };:",
            ":(){ :|:& }; :",
            "bomb(){ bomb|bomb& }; bomb",
        ]
        for fb in fork_bombs:
            lvl, score, reason = self.validator.evaluate_safety(fb)
            self.assertEqual(lvl, SafetyLevel.DESTRUCTIVE, f"Failed to block fork bomb: {fb}")

    def test_safe_read_only_allowed(self):
        safe_cmds = [
            "cat /var/log/syslog",
            "journalctl -u nginx -n 50",
            "ps aux --sort=-%cpu",
            "df -h",
            "ss -tulpn",
            "uptime",
            "uname -a",
            "dmesg -T",
        ]
        for cmd in safe_cmds:
            lvl, score, reason = self.validator.evaluate_safety(cmd)
            self.assertEqual(lvl, SafetyLevel.READ_ONLY, f"Incorrectly marked unsafe: {cmd}")


if __name__ == "__main__":
    unittest.main()
