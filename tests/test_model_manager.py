"""Unit tests for Model Manager, Downloader, GGUF Header validation, and LlamaCppProvider."""

import os
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from ops_assistant.model_manager.downloader import ModelDownloader, DEFAULT_MODELS, get_default_models_dir
from ops_assistant.agent import LlamaCppProvider, OpsAssistantAgent, SafetyLevel

class TestModelManager(unittest.TestCase):
    def setUp(self):
        self.downloader = ModelDownloader()

    def test_list_available_models(self):
        models = self.downloader.list_available_models()
        self.assertIn("qwen2.5-coder-0.5b", models)
        self.assertIn("smollm2-360m", models)
        self.assertIn("is_downloaded", models["qwen2.5-coder-0.5b"])
        self.assertIn("filename", models["qwen2.5-coder-0.5b"])

    def test_get_active_model_path(self):
        active = self.downloader.get_active_model_path()
        # If downloaded, returns Path, else None
        if (self.downloader.target_dir / "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf").exists():
            self.assertIsNotNone(active)
            self.assertTrue(active.exists())

    def test_verify_gguf_header_valid(self):
        qwen_path = self.downloader.target_dir / "qwen2.5-coder-0.5b-instruct-q4_k_m.gguf"
        if qwen_path.exists():
            header = self.downloader.verify_gguf_header(qwen_path)
            self.assertTrue(header["valid"])
            self.assertEqual(header["magic"], "GGUF")
            self.assertGreaterEqual(header["version"], 2)
            self.assertGreater(header["tensor_count"], 0)

    def test_verify_gguf_header_nonexistent(self):
        header = self.downloader.verify_gguf_header(Path("/nonexistent/file.gguf"))
        self.assertFalse(header["valid"])
        self.assertIn("does not exist", header["error"])

    def test_llamacpp_provider_availability_check(self):
        provider = LlamaCppProvider(model_path="/nonexistent/model.gguf")
        avail, msg = provider.is_available()
        self.assertFalse(avail)
        self.assertIn("not found", msg)

    def test_llamacpp_provider_mock_diagnosis(self):
        provider = LlamaCppProvider(model_path="/dummy/model.gguf")
        # Mock internal _llm
        mock_llm = MagicMock()
        mock_llm.return_value = {
            "choices": [
                {
                    "text": '{"symptom": "Custom LLM Symptom", "root_cause": "Custom Root Cause", "rationale": "Custom Rationale", "proposed_commands": [["sudo systemctl restart custom", "MODIFYING", 0.35, "Restart custom service"]], "confidence": 0.95}'
                }
            ]
        }
        provider._llm = mock_llm

        res = provider.generate_diagnosis("Novel anomaly occurred", {"subsystem": "custom"})
        self.assertIsNotNone(res)
        self.assertEqual(res.get("symptom"), "Custom LLM Symptom")
        self.assertEqual(res.get("root_cause"), "Custom Root Cause")
        self.assertEqual(len(res.get("proposed_commands", [])), 1)

    def test_agent_with_mock_llamacpp_provider(self):
        mock_provider = MagicMock()
        mock_provider.generate_diagnosis.return_value = {
            "symptom": "LLM diagnosed port leak",
            "root_cause": "Zombie sockets holding port descriptor",
            "rationale": "Kernel socket table indicates orphaned connection",
            "proposed_commands": [
                ["sudo fuser -k 9000/tcp", "HIGH_RISK", 0.70, "Kill socket holders"]
            ],
            "confidence": 0.92
        }

        agent = OpsAssistantAgent(llm_provider=mock_provider)
        rep = agent.diagnose("Unusual network hang on proprietary port 9000", custom_logs=[])
        self.assertIn("LLM diagnosed port leak", rep.explanation.symptom)
        self.assertEqual(rep.explanation.confidence_score, 0.92)
        self.assertEqual(len(rep.explanation.proposed_commands), 1)
        self.assertEqual(rep.explanation.proposed_commands[0].safety_level, SafetyLevel.HIGH_RISK)

if __name__ == "__main__":
    unittest.main()
