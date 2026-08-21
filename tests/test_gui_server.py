"""Unit tests for GUI REST endpoints and SSE server."""

import unittest
import threading
import time
import urllib.request
import urllib.error
import json

from ops_assistant.gui.server import start_gui_server
from ops_assistant.agent import OpsAssistantAgent


class TestGUIServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.agent = OpsAssistantAgent(llm_provider=None)
        # Use an ephemeral port or port 9922 for testing
        cls.server, cls.url = start_gui_server(
            host="127.0.0.1",
            port=9922,
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

    def _get(self, endpoint):
        req = urllib.request.Request(f"{self.url}{endpoint}", headers={"Connection": "close"})
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def _post(self, endpoint, data):
        req = urllib.request.Request(
            f"{self.url}{endpoint}",
            data=json.dumps(data).encode("utf-8"),
            headers={"Content-Type": "application/json", "Connection": "close"}
        )
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_static_index(self):
        req = urllib.request.Request(f"{self.url}/", headers={"Connection": "close"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode("utf-8")
            self.assertIn("Linux Operations Assistant", content)

    def test_static_head(self):
        req = urllib.request.Request(f"{self.url}/", headers={"Connection": "close"}, method="HEAD")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("no-store", resp.headers.get("Cache-Control", ""))

    def test_static_cache_headers(self):
        req = urllib.request.Request(f"{self.url}/static/styles.css", headers={"Connection": "close"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            self.assertIn("no-store", resp.headers.get("Cache-Control", ""))
            self.assertEqual(resp.headers.get("Pragma"), "no-cache")

    def test_api_health(self):
        status, data = self._get("/api/health")
        self.assertEqual(status, 200)
        self.assertIn("hostname", data)
        self.assertIn("cpu", data)
        self.assertIn("memory", data)

    def test_api_services(self):
        status, data = self._get("/api/services")
        self.assertEqual(status, 200)
        self.assertIn("services", data)

    def test_api_processes(self):
        status, data = self._get("/api/processes?n=5")
        self.assertEqual(status, 200)
        self.assertIn("processes", data)

    def test_api_taxonomy_scenarios(self):
        status, data = self._get("/api/taxonomy/scenarios")
        self.assertEqual(status, 200)
        self.assertIn("scenarios", data)
        self.assertEqual(len(data["scenarios"]), 16)

    def test_api_agent_chat(self):
        status, data = self._post("/api/agent/chat", {"prompt": "open browser to https://python.org"})
        self.assertEqual(status, 200)
        self.assertIn("summary", data)
        self.assertEqual(str(data.get("intent")).lower(), "desktop_open_browser")

    def test_api_execute_safe(self):
        status, data = self._post("/api/execute", {"command": "echo 'hello test'", "dry_run": False})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("returncode"), 0)
        self.assertIn("hello test", data.get("stdout"))
        self.assertIn("latency_ms", data)

    def test_api_execute_dry_run(self):
        status, data = self._post("/api/execute", {"command": "sudo systemctl restart nginx", "dry_run": True})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("dry_run"))

    def test_api_execute_destructive_blocked(self):
        try:
            status, data = self._post("/api/execute", {"command": "sudo rm -rf /"})
            self.assertEqual(status, 403)
            self.assertTrue(data.get("blocked"))
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 403)
            err_data = json.loads(e.read().decode("utf-8"))
            self.assertTrue(err_data.get("blocked"))
            self.assertEqual(err_data.get("safety_level"), "DESTRUCTIVE")

    def test_api_rollback(self):
        status, data = self._post("/api/rollback", {"rollback_command": "echo 'rollback_test'"})
        self.assertEqual(status, 200)
        self.assertTrue(data.get("success"))
        self.assertIn("rollback_test", data.get("stdout"))

    def test_api_distro(self):
        status, data = self._get("/api/distro")
        self.assertEqual(status, 200)
        self.assertIn("family_id", data)

    def test_api_storage_analysis(self):
        status, data = self._get("/api/storage/analysis?path=/")
        self.assertEqual(status, 200)
        self.assertIn("disks", data)


if __name__ == "__main__":
    unittest.main()