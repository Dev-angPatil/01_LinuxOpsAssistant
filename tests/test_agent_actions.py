"""Unit tests for Unified Natural Language Action Execution across all intents."""

import unittest
from ops_assistant.agent import OpsAssistantAgent
from ops_assistant.models import SafetyLevel
from ops_assistant.tools.safety import CommandSafetyValidator
from ops_assistant.tools.executor import SafeExecutor


class TestAgentActions(unittest.TestCase):
    def setUp(self):
        self.agent = OpsAssistantAgent(llm_provider=None)

    def test_desktop_actions_preview_and_exec(self):
        r1 = self.agent.execute_agent_action("open folder ~/Downloads", execute=False)
        self.assertEqual(r1["intent"], "desktop_open_folder")
        self.assertEqual(r1["safety_level"], SafetyLevel.READ_ONLY.value)
        self.assertIn("xdg-open", r1["command"])

        r2 = self.agent.execute_agent_action("open browser https://google.com", execute=False)
        self.assertEqual(r2["intent"], "desktop_open_browser")
        self.assertIn("https://google.com", r2["command"])

    def test_storage_actions(self):
        r1 = self.agent.execute_agent_action("clean logs and temporary files", execute=False)
        self.assertEqual(r1["intent"], "storage_clean")
        self.assertTrue(r1["requires_permission"])

        r2 = self.agent.execute_agent_action("organise directory /tmp", execute=False)
        self.assertEqual(r2["intent"], "storage_organise")
        self.assertTrue(r2["requires_permission"])

        r3 = self.agent.execute_agent_action("analyze disk usage", execute=False)
        self.assertEqual(r3["intent"], "storage_analyse")
        self.assertEqual(r3["safety_level"], SafetyLevel.READ_ONLY.value)

        r4 = self.agent.execute_agent_action("find large files", execute=False)
        self.assertEqual(r4["intent"], "storage_find_large")
        self.assertEqual(r4["safety_level"], SafetyLevel.READ_ONLY.value)

    def test_process_actions(self):
        r1 = self.agent.execute_agent_action("list processes", execute=True)
        self.assertEqual(r1["intent"], "process_list")
        self.assertIsInstance(r1["output"], list)

        r2 = self.agent.execute_agent_action("kill process 99999", execute=False)
        self.assertEqual(r2["intent"], "process_kill")
        self.assertTrue(r2["requires_permission"])
        self.assertEqual(r2["safety_level"], SafetyLevel.HIGH_RISK.value)

        r3 = self.agent.execute_agent_action("kill process nginx", execute=False)
        self.assertEqual(r3["intent"], "process_kill")
        self.assertIn("pkill", r3["command"])

    def test_service_actions(self):
        r1 = self.agent.execute_agent_action("status of nginx", execute=False)
        self.assertEqual(r1["intent"], "service_status")
        self.assertEqual(r1["safety_level"], SafetyLevel.READ_ONLY.value)

        r2 = self.agent.execute_agent_action("restart nginx", execute=False)
        self.assertEqual(r2["intent"], "service_restart")
        self.assertTrue(r2["requires_permission"])
        self.assertEqual(r2["safety_level"], SafetyLevel.MODIFYING.value)

        r3 = self.agent.execute_agent_action("start nginx", execute=False)
        self.assertEqual(r3["intent"], "service_start")
        self.assertEqual(r3["rollback_command"], "sudo systemctl stop 'nginx'")

        r4 = self.agent.execute_agent_action("stop nginx", execute=False)
        self.assertEqual(r4["intent"], "service_stop")
        self.assertEqual(r4["rollback_command"], "sudo systemctl start 'nginx'")

    def test_network_actions(self):
        r1 = self.agent.execute_agent_action("ping google.com", execute=False)
        self.assertEqual(r1["intent"], "network_ping")
        self.assertEqual(r1["safety_level"], SafetyLevel.READ_ONLY.value)

        r2 = self.agent.execute_agent_action("dns lookup github.com", execute=False)
        self.assertEqual(r2["intent"], "network_dns")

        r3 = self.agent.execute_agent_action("allow port 8080 in firewall", execute=False)
        self.assertEqual(r3["intent"], "firewall_allow")
        self.assertEqual(r3["rollback_command"], "sudo ufw delete allow 8080/tcp")

        r4 = self.agent.execute_agent_action("deny port 22 in firewall", execute=False)
        self.assertEqual(r4["intent"], "firewall_deny")
        self.assertEqual(r4["rollback_command"], "sudo ufw delete deny 22/tcp")

    def test_security_actions(self):
        r1 = self.agent.execute_agent_action("run security audit", execute=False)
        self.assertEqual(r1["intent"], "security_audit")

        r2 = self.agent.execute_agent_action("check for ssh brute force attacks", execute=False)
        self.assertEqual(r2["intent"], "security_bruteforce")

        r3 = self.agent.execute_agent_action("audit suid binaries", execute=False)
        self.assertEqual(r3["intent"], "security_suid")

    def test_system_and_log_actions(self):
        r1 = self.agent.execute_agent_action("show system info", execute=False)
        self.assertEqual(r1["intent"], "system_info")

        r2 = self.agent.execute_agent_action("system uptime", execute=False)
        self.assertEqual(r2["intent"], "system_uptime")

        r3 = self.agent.execute_agent_action("show error logs", execute=False)
        self.assertEqual(r3["intent"], "logs_errors")

        r4 = self.agent.execute_agent_action("show kernel logs", execute=False)
        self.assertEqual(r4["intent"], "logs_kernel")

        r5 = self.agent.execute_agent_action("who is logged in", execute=False)
        self.assertEqual(r5["intent"], "user_who")

    def test_validator_and_executor_helpers(self):
        val = CommandSafetyValidator.validate("echo 123")
        self.assertEqual(val.level, SafetyLevel.READ_ONLY)
        self.assertFalse(val.is_destructive)

        val_dest = CommandSafetyValidator.validate("rm -rf /")
        self.assertEqual(val_dest.level, SafetyLevel.DESTRUCTIVE)
        self.assertTrue(val_dest.is_destructive)

        executor = SafeExecutor()
        res = executor.execute_command("echo 'test_exec'", dry_run=False)
        self.assertEqual(res["returncode"], 0)
        self.assertIn("test_exec", res["stdout"])

        res_rb = executor.rollback("echo 'rollback_exec'")
        self.assertEqual(res_rb["returncode"], 0)


if __name__ == "__main__":
    unittest.main()
