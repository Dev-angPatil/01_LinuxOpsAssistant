"""Unit tests for Qwen AI Model Provider & Natural Language Operations."""

import unittest
import os
import tempfile
import shutil
from pathlib import Path
from ops_assistant.agent import OpsAssistantAgent, QwenProvider, LlamaCppProvider
from ops_assistant.nlp.nl_compiler import NaturalLanguageCompiler
from ops_assistant.nlp.intent_router import IntentRouter, IntentType
from ops_assistant.config import get_config


class TestQwenProvider(unittest.TestCase):
    def setUp(self):
        self.provider = QwenProvider()
        self.agent = OpsAssistantAgent(llm_provider="qwen")

    def test_qwen_provider_initialization(self):
        self.assertIsNotNone(self.provider)
        self.assertEqual(self.provider.model_key, "qwen2.5-coder-1.5b")
        avail, msg = self.provider.is_available()
        self.assertTrue(avail)
        self.assertIn("Ready", msg)

    def test_qwen_generate_command_folder_creation(self):
        res = self.provider.generate_command("inside Divya create one folder name as DBMS")
        self.assertIsNotNone(res)
        self.assertIn("command", res)
        self.assertIn("mkdir", res["command"])
        self.assertIn("DBMS", res["command"])
        self.assertIn("Divya", res["command"])

    def test_qwen_generate_command_desktop_browser(self):
        res = self.provider.generate_command("open YouTube")
        self.assertIsNotNone(res)
        self.assertIn("xdg-open", res["command"])
        self.assertIn("youtube.com", res["command"])

    def test_qwen_generate_command_system_resources(self):
        cpu_res = self.provider.generate_command("check cpu usage")
        self.assertIsNotNone(cpu_res)
        self.assertIn("top", cpu_res["command"])

        ram_res = self.provider.generate_command("check ram uses")
        self.assertIsNotNone(ram_res)
        self.assertIn("free", ram_res["command"])

        disk_res = self.provider.generate_command("check disk space")
        self.assertIsNotNone(disk_res)
        self.assertIn("df", disk_res["command"])

    def test_qwen_generate_command_network_ports(self):
        port_res = self.provider.generate_command("show all listening ports")
        self.assertIsNotNone(port_res)
        self.assertIn("ss", port_res["command"])

    def test_qwen_agent_execute_agent_action_directory(self):
        test_dir = tempfile.mkdtemp(prefix="ops_test_qwen_")
        try:
            query = f"inside {test_dir} create one folder name as DBMS"
            result = self.agent.execute_agent_action(query, execute=True)
            self.assertEqual(result["intent"], "dir_create")
            self.assertIn("mkdir", result["command"])
            expected_folder = os.path.join(test_dir, "DBMS")
            self.assertTrue(os.path.isdir(expected_folder))
        finally:
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)

    def test_qwen_agent_interpret_command(self):
        plan = self.agent.interpret_command("inside Divya create one folder name as DBMS")
        self.assertIsNotNone(plan)
        self.assertIn("understanding", plan)
        self.assertIn("plan_steps", plan)
        self.assertGreater(len(plan["plan_steps"]), 0)
        self.assertIn("mkdir", plan["plan_steps"][0]["command"])

    def test_llama_cpp_provider_inherits_qwen(self):
        llama_p = LlamaCppProvider()
        self.assertIsInstance(llama_p, QwenProvider)
        avail, _ = llama_p.is_available()
        self.assertTrue(avail)


if __name__ == "__main__":
    unittest.main()
