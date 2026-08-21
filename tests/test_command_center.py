"""
Tests for the CommandCenter API endpoints.
Starts the server on port 9923 (avoids colliding with test_gui_server.py on 9922).
"""

import json
import time
import queue
import threading
import unittest
from unittest.mock import MagicMock

from ops_assistant.gui.server import (
    OpsAssistantHandler,
    start_gui_server,
    _COMMAND_SESSIONS,
    _SESSIONS_LOCK,
    _create_session,
    _get_session,
)


def _make_mock_agent(safety_level="READ_ONLY", requires_confirmation=False):
    agent = MagicMock()
    agent.interpret_command.return_value = {
        "understanding": "You want me to show current memory usage.",
        "plan_steps": [{
            "index": 0,
            "description": "Display free memory",
            "command": "free -h",
            "safety_level": safety_level,
            "risk_score": 0.02,
        }],
        "requires_confirmation": requires_confirmation,
        "safety_level": safety_level,
        "intent": "MONITOR_MEMORY",
        "confidence": 0.98,
    }
    return agent


class TestSessionStore(unittest.TestCase):
    def setUp(self):
        with _SESSIONS_LOCK:
            _COMMAND_SESSIONS.clear()

    def test_create_and_get(self):
        sid = _create_session({"text": "hi", "plan_steps": [], "requires_confirmation": False})
        sess = _get_session(sid)
        self.assertIsNotNone(sess)
        self.assertEqual(sess["text"], "hi")

    def test_missing_returns_none(self):
        self.assertIsNone(_get_session("bad-id"))

    def test_has_queue(self):
        sid = _create_session({"text": "t"})
        sess = _get_session(sid)
        self.assertIsInstance(sess["events_queue"], queue.Queue)

    def test_ttl_expiry(self):
        sid = _create_session({"text": "x"})
        with _SESSIONS_LOCK:
            _COMMAND_SESSIONS[sid]["created_at"] = time.time() - 400
        self.assertIsNone(_get_session(sid))


class TestInterpretCommandMethod(unittest.TestCase):
    def _agent(self, safety_level="READ_ONLY", planned_commands=None):
        from ops_assistant.agent import OpsAssistantAgent, SafetyLevel
        a = MagicMock(spec=OpsAssistantAgent)
        a.execute_agent_action.return_value = {
            "summary": "Showing memory.",
            "intent": "MONITOR_MEMORY",
            "confidence": 0.95,
            "safety_level": safety_level,
            "risk_score": 0.05,
            "command": "free -h",
            "command_description": "Display free memory",
            "planned_commands": planned_commands or [],
            "requires_permission": safety_level in ("HIGH_RISK", "DESTRUCTIVE"),
        }
        a.interpret_command = OpsAssistantAgent.interpret_command.__get__(a)
        return a

    def test_readonly_no_confirm(self):
        self.assertFalse(self._agent("READ_ONLY").interpret_command("show mem")["requires_confirmation"])

    def test_modifying_no_confirm(self):
        self.assertFalse(self._agent("MODIFYING").interpret_command("restart svc")["requires_confirmation"])

    def test_high_risk_confirm(self):
        self.assertTrue(self._agent("HIGH_RISK").interpret_command("del logs")["requires_confirmation"])

    def test_destructive_confirm(self):
        self.assertTrue(self._agent("DESTRUCTIVE").interpret_command("rm -rf")["requires_confirmation"])

    def test_fallback_single_command(self):
        result = self._agent(planned_commands=[]).interpret_command("show mem")
        self.assertEqual(len(result["plan_steps"]), 1)
        self.assertEqual(result["plan_steps"][0]["command"], "free -h")


TEST_PORT = 9923


class TestCommandCenterHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._base_agent = _make_mock_agent()
        cls.server, cls.url = start_gui_server(
            host="127.0.0.1", port=TEST_PORT, open_browser=False, agent=cls._base_agent
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def _post(self, path, payload):
        import urllib.request, urllib.error
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"{self.url}{path}",
            data=data,
            headers={"Content-Type": "application/json", "Connection": "close"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_interpret_has_session_id(self):
        s, b = self._post("/api/command/interpret", {"text": "show memory"})
        self.assertEqual(s, 200)
        self.assertIn("session_id", b)

    def test_interpret_has_understanding(self):
        s, b = self._post("/api/command/interpret", {"text": "show memory"})
        self.assertEqual(s, 200)
        self.assertGreater(len(b.get("understanding", "")), 0)

    def test_interpret_has_plan_steps(self):
        s, b = self._post("/api/command/interpret", {"text": "show memory"})
        self.assertEqual(s, 200)
        self.assertIsInstance(b.get("plan_steps"), list)

    def test_interpret_empty_text_fails(self):
        s, _ = self._post("/api/command/interpret", {"text": ""})
        self.assertNotEqual(s, 200)

    def test_execute_readonly_succeeds(self):
        _, interp = self._post("/api/command/interpret", {"text": "show memory"})
        s, b = self._post("/api/command/execute", {"session_id": interp["session_id"], "confirmed": False})
        self.assertEqual(s, 200)
        self.assertTrue(b.get("success"))

    def test_execute_missing_session_404(self):
        s, _ = self._post("/api/command/execute", {"session_id": "no-such-id", "confirmed": False})
        self.assertEqual(s, 404)

    def test_high_risk_blocked_without_confirmed(self):
        OpsAssistantHandler.agent = _make_mock_agent("HIGH_RISK", requires_confirmation=True)
        try:
            _, interp = self._post("/api/command/interpret", {"text": "delete logs"})
            s, b = self._post("/api/command/execute", {"session_id": interp["session_id"], "confirmed": False})
            self.assertEqual(s, 403)
            self.assertTrue(b.get("blocked"))
        finally:
            OpsAssistantHandler.agent = self._base_agent

    def test_high_risk_allowed_with_confirmed(self):
        OpsAssistantHandler.agent = _make_mock_agent("HIGH_RISK", requires_confirmation=True)
        try:
            _, interp = self._post("/api/command/interpret", {"text": "delete logs"})
            s, b = self._post("/api/command/execute", {"session_id": interp["session_id"], "confirmed": True})
            self.assertEqual(s, 200)
            self.assertTrue(b.get("success"))
        finally:
            OpsAssistantHandler.agent = self._base_agent

    def test_events_log_order(self):
        _, interp = self._post("/api/command/interpret", {"text": "show memory"})
        sid = interp["session_id"]
        self._post("/api/command/execute", {"session_id": sid, "confirmed": False})
        time.sleep(1.5)
        sess = _get_session(sid)
        self.assertIsNotNone(sess)
        types = [e["type"] for e in sess.get("events_log", [])]
        self.assertEqual(types[0], "understanding", msg=f"got: {types}")
        self.assertIn("result", types, msg=f"got: {types}")
        self.assertEqual(types[-1], "result", msg=f"got: {types}")


if __name__ == "__main__":
    unittest.main()
