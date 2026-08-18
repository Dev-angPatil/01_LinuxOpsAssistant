"""Unit tests for Diagnostic Reasoning Agent and XAI Explainer."""

import unittest
from ops_assistant.agent import OpsAssistantAgent
from ops_assistant.models import LogRecord, SafetyLevel

class TestAgentAndXAI(unittest.TestCase):
    def setUp(self):
        self.agent = OpsAssistantAgent()

    def test_diagnose_port_conflict(self):
        custom_logs = [
            LogRecord(
                timestamp="2026-08-18T00:00:00Z",
                source="journald",
                priority="3",
                unit="nginx.service",
                message="[emerg] bind() to 0.0.0.0:80 failed (98: Address already in use)"
            )
        ]
        rep = self.agent.diagnose("Why is NGINX failing to start?", custom_logs=custom_logs)
        self.assertEqual(rep.target_subsystem, "nginx")
        self.assertIn("bound", rep.explanation.root_cause.lower())
        self.assertGreaterEqual(rep.explanation.confidence_score, 0.90)
        self.assertGreater(len(rep.explanation.proposed_commands), 0)

        # Check flag breakdowns in proposed commands
        ss_cmd = [c for c in rep.explanation.proposed_commands if "ss" in c.command][0]
        self.assertGreater(len(ss_cmd.flag_breakdown), 0)

    def test_diagnose_oom_crash(self):
        custom_logs = [
            LogRecord(
                timestamp="2026-08-18T00:00:00Z",
                source="dmesg",
                priority="3",
                unit="kernel",
                message="Out of memory: Killed process 4192 (postgres) total-vm:8192000kB"
            )
        ]
        rep = self.agent.diagnose("PostgreSQL crashed unexpectedly", custom_logs=custom_logs)
        self.assertEqual(rep.target_subsystem, "postgres")
        self.assertIn("out-of-memory", rep.explanation.root_cause.lower())
        self.assertTrue(any("free" in c.command for c in rep.explanation.proposed_commands))

    def test_diagnose_disk_exhaustion(self):
        custom_logs = [
            LogRecord(
                timestamp="2026-08-18T00:00:00Z",
                source="journald",
                priority="3",
                unit="app.service",
                message="IOError: [Errno 28] No space left on device"
            )
        ]
        rep = self.agent.diagnose("Cannot write to log files", custom_logs=custom_logs)
        self.assertIn("exhausted", rep.explanation.root_cause.lower())
        self.assertTrue(any("df" in c.command for c in rep.explanation.proposed_commands))

    def test_all_16_taxonomy_classes(self):
        taxonomy_samples = {
            "PORT_CONFLICT": "Address already in use on port 80",
            "PERMISSION_DENIED": "Permission denied opening /var/log/audit.log",
            "OOM_KILL": "kernel invoked oom-killer: Killed process 1024",
            "DISK_EXHAUSTION": "write error: No space left on device",
            "INODE_EXHAUSTION": "cannot create directory: No space left on device out of inodes",
            "CONFIG_SYNTAX_ERROR": "nginx syntax error directive is not allowed here",
            "SSL_CERT_ERROR": "SSL routines: certificate has expired on port 443",
            "DNS_RESOLUTION_FAILURE": "Temporary failure in name resolution for upstream",
            "DPKG_LOCK_BLOCKED": "Could not get lock /var/lib/dpkg/lock-frontend",
            "SYSTEMD_CRASH_LOOP": "Unit app.service entered failed state Start request repeated too quickly",
            "DB_CONN_EXHAUSTION": "FATAL: remaining connection slots are reserved for non-replication superuser",
            "FIREWALL_PORT_BLOCKED": "Connection refused on port 8080 iptables DROP",
            "ZOMBIE_PROCESS_ACCUMULATION": "High number of defunct zombie processes detected",
            "IOWAIT_BOTTLENECK": "High iowait on NVMe drive task blocked for more than 120 seconds",
            "SELINUX_APPARMOR_DENIAL": "audit: type=1400 apparmor='DENIED' operation='open'",
            "NTP_CLOCK_DRIFT": "Server has gone too long without receiving time clock skew detected"
        }

        for tax_id, query in taxonomy_samples.items():
            rep = self.agent.diagnose(query)
            self.assertIsNotNone(rep.explanation.symptom)
            self.assertIsNotNone(rep.explanation.root_cause)
            self.assertGreaterEqual(rep.explanation.confidence_score, 0.85)
            self.assertGreater(len(rep.explanation.proposed_commands), 0)

    def test_rollback_generation(self):
        xai = self.agent.explainer
        rollback, rat = xai.generate_rollback_command("sudo systemctl start nginx")
        self.assertEqual(rollback, "sudo systemctl stop nginx")
        self.assertIsNotNone(rat)

        rollback_fw, _ = xai.generate_rollback_command("sudo ufw allow 80/tcp")
        self.assertEqual(rollback_fw, "sudo ufw delete allow 80/tcp")

    def test_report_serialization(self):
        rep = self.agent.diagnose("Why is NGINX failing to bind?")
        d = rep.to_dict()
        self.assertIsInstance(d, dict)
        self.assertIn("query", d)
        self.assertIn("explanation", d)
        self.assertIn("latency_ms", d)

if __name__ == "__main__":
    unittest.main()

