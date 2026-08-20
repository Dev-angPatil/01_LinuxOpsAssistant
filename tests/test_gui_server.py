"""Unit tests for GUI REST endpoints and SSE server."""

import unittest
import threading
import time
import urllib.request
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


if __name__ == "__main__":
    unittest.main()