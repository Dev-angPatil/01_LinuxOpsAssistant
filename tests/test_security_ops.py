"""Unit tests for Security, SSH Configuration & Brute-Force Auditing."""

import os
import unittest
import tempfile
from unittest.mock import patch
from ops_assistant.tools import security_ops


class TestSecurityOps(unittest.TestCase):
    def test_inspect_ssh_security_secure_config(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(
                "Port 2222\n"
                "PermitRootLogin no\n"
                "PasswordAuthentication no\n"
                "X11Forwarding no\n"
                "MaxAuthTries 3\n"
            )
            cfg_path = f.name

        try:
            res = security_ops.inspect_ssh_security(cfg_path)
            self.assertTrue(res["success"])
            self.assertEqual(res["security_score"], 100.0)
            self.assertEqual(len(res["recommendations"]), 0)
        finally:
            if os.path.exists(cfg_path):
                os.unlink(cfg_path)

    def test_inspect_ssh_security_vulnerable_config(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(
                "Port 22\n"
                "PermitRootLogin yes\n"
                "PasswordAuthentication yes\n"
                "X11Forwarding yes\n"
                "MaxAuthTries 10\n"
            )
            cfg_path = f.name

        try:
            res = security_ops.inspect_ssh_security(cfg_path)
            self.assertTrue(res["success"])
            self.assertLess(res["security_score"], 50.0)
            self.assertGreater(len(res["recommendations"]), 0)
        finally:
            if os.path.exists(cfg_path):
                os.unlink(cfg_path)

    @patch("ops_assistant.tools.security_ops._run_cmd")
    def test_detect_ssh_bruteforce_attack(self, mock_run):
        mock_journal = (
            "Failed password for root from 192.168.1.100 port 54321 ssh2\n" * 15 +
            "Failed password for admin from 10.0.0.5 port 12345 ssh2\n" * 5
        )
        mock_run.return_value = (0, mock_journal, "")

        with patch("os.path.exists", return_value=False):
            with patch("shutil.which", return_value="/usr/bin/journalctl"):
                res = security_ops.detect_ssh_bruteforce(hours=1)
                self.assertTrue(res["success"])
                self.assertEqual(res["total_failed_attempts"], 20)
                self.assertEqual(res["threat_level"], "ELEVATED")
                self.assertEqual(res["top_offending_ips"][0]["ip"], "192.168.1.100")
                self.assertEqual(res["top_offending_ips"][0]["attempts"], 15)

    def test_audit_suid_binaries_live(self):
        res = security_ops.audit_suid_binaries()
        self.assertTrue(res["success"])
        self.assertIsInstance(res["total_suid_count"], int)
        self.assertIsInstance(res["anomalous_suid_count"], int)
        self.assertIn(res["status"], ["CLEAN", "ATTENTION_REQUIRED"])

    @patch("ops_assistant.tools.network_ops.list_listening_ports", return_value=[{"port": "22"}, {"port": "80"}])
    @patch("ops_assistant.tools.network_ops.get_firewall_status", return_value={"status": "active", "firewall": "ufw"})
    @patch("ops_assistant.tools.security_ops.inspect_ssh_security", return_value={"security_score": 90.0})
    @patch("ops_assistant.tools.security_ops.detect_ssh_bruteforce", return_value={"threat_level": "NORMAL", "total_failed_attempts": 0})
    @patch("ops_assistant.tools.security_ops.audit_suid_binaries", return_value={"anomalous_suid_count": 0, "total_suid_count": 10})
    def test_audit_security_consolidated(self, mock_suid, mock_bf, mock_ssh, mock_fw, mock_ports):
        res = security_ops.audit_security()
        self.assertTrue(res["success"])
        self.assertEqual(res["overall_status"], "HEALTHY")
        self.assertEqual(res["listening_ports_count"], 2)


if __name__ == "__main__":
    unittest.main()
