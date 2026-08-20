"""Unit and integration tests for Setup Wizard, ConfigManager, and Hardware-Adaptive Model Setup."""

import json
import os
import tempfile
import unittest
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

from ops_assistant.config import ConfigManager, DEFAULT_CONFIG
from ops_assistant.hardware.advisor import HardwareAdvisor, ModelTier
from ops_assistant.hardware.profiler import HardwareProfile, CPUInfo, MemoryInfo, GPUInfo, StorageInfo
from ops_assistant.model_manager.downloader import ModelDownloader
from ops_assistant.cli import run_setup_wizard
from ops_assistant.gui.server import start_gui_server


class TestConfigManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"
        self.mgr = ConfigManager(config_file=self.config_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_default_config_loading(self):
        cfg = self.mgr.load()
        self.assertFalse(cfg["setup_completed"])
        self.assertEqual(cfg["provider"], "auto")
        self.assertFalse(self.mgr.is_setup_completed())

    def test_save_and_reload(self):
        cfg = self.mgr.load()
        cfg["setup_completed"] = True
        cfg["provider"] = "gguf"
        cfg["active_model_key"] = "qwen2.5-coder-0.5b"
        self.assertTrue(self.mgr.save(cfg))

        reloaded = self.mgr.load()
        self.assertTrue(reloaded["setup_completed"])
        self.assertEqual(reloaded["active_model_key"], "qwen2.5-coder-0.5b")
        self.assertTrue(self.mgr.is_setup_completed())

    def test_set_setup_completed_helper(self):
        cfg = self.mgr.set_setup_completed(
            provider="gguf",
            model_key="smollm2-360m",
            model_path="/models/smollm2.gguf",
            hardware_tier="Tier-1-Constrained",
            threads=2,
            ctx_size=1024,
            gpu_layers=0,
        )
        self.assertTrue(cfg["setup_completed"])
        self.assertEqual(cfg["active_model_key"], "smollm2-360m")
        self.assertEqual(cfg["recommended_threads"], 2)
        self.assertEqual(cfg["recommended_ctx_size"], 1024)
        self.assertTrue(self.mgr.is_setup_completed())


class TestModelDownloaderAsync(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dl = ModelDownloader(target_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_has_any_model_installed_empty(self):
        self.assertFalse(self.dl.has_any_model_installed())

    def test_has_any_model_installed_with_file(self):
        fake_model = Path(self.temp_dir.name) / "test.gguf"
        with open(fake_model, "wb") as f:
            f.write(b"GGUF" + b"\x00" * (2 * 1024 * 1024))
        self.assertTrue(self.dl.has_any_model_installed())

    def test_start_background_download_invalid_key(self):
        res = self.dl.start_background_download("invalid-key-xyz")
        self.assertFalse(res["success"])
        self.assertIn("Unknown model key", res["error"])

    @patch.object(ModelDownloader, "download_model")
    def test_start_background_download_mock(self, mock_dl):
        fake_path = Path(self.temp_dir.name) / "test.gguf"
        mock_dl.return_value = fake_path

        res = self.dl.start_background_download("smollm2-360m")
        self.assertTrue(res["success"])
        self.assertIn("status", res)
        import time
        time.sleep(0.1)
        prog = self.dl.get_download_progress("smollm2-360m")
        self.assertIsNotNone(prog)


class TestCLISetupWizard(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.cfg_file = Path(self.temp_dir.name) / "config.json"
        self.cfg_mgr = ConfigManager(config_file=self.cfg_file)
        self.dl = ModelDownloader(target_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("ops_assistant.cli.set_setup_completed")
    def test_setup_wizard_choice_deterministic(self, mock_set_completed):
        inputs = iter(["3"])
        res = run_setup_wizard(
            downloader=self.dl,
            interactive_input=lambda prompt: next(inputs),
        )
        self.assertTrue(res)
        mock_set_completed.assert_called_once()
        kwargs = mock_set_completed.call_args.kwargs
        self.assertEqual(kwargs.get("provider"), "deterministic")

    @patch("ops_assistant.cli.set_setup_completed")
    def test_setup_wizard_choice_skip(self, mock_set_completed):
        inputs = iter(["5"])
        res = run_setup_wizard(
            downloader=self.dl,
            interactive_input=lambda prompt: next(inputs),
        )
        self.assertFalse(res)
        mock_set_completed.assert_not_called()


class TestGUISetupEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import threading
        import time
        from ops_assistant.agent import OpsAssistantAgent
        cls.agent = OpsAssistantAgent(llm_provider=None)
        cls.server, cls.url = start_gui_server(
            host="127.0.0.1",
            port=9944,
            open_browser=False,
            agent=cls.agent
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_api_setup_status(self):
        req = urllib.request.Request(f"{self.url}/api/setup/status", headers={"Connection": "close"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("setup_completed", data)
            self.assertIn("hardware", data)
            self.assertIn("recommended_model", data)
            self.assertIn("catalog", data)
            self.assertIn("installed_models", data)

    def test_api_models_list(self):
        req = urllib.request.Request(f"{self.url}/api/models/list", headers={"Connection": "close"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("models", data)

    def test_api_models_download_progress(self):
        req = urllib.request.Request(f"{self.url}/api/models/download/progress", headers={"Connection": "close"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertIn("downloads", data)

    def test_api_setup_apply(self):
        payload = json.dumps({"provider": "deterministic"}).encode()
        req = urllib.request.Request(
            f"{self.url}/api/setup/apply",
            data=payload,
            headers={"Content-Type": "application/json", "Connection": "close"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode())
            self.assertTrue(data.get("success"))
            self.assertEqual(data["config"]["provider"], "deterministic")


if __name__ == "__main__":
    unittest.main()
