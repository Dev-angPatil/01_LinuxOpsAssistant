#!/usr/bin/env python3
"""
Unit tests for newly added capabilities:
- Multi-language project dependency detection and venv creation (project_ops)
- Persistent SQLite History Database (history_db)
- GeminiProvider and 3-layer architecture (agent)
- CommandExplainer & ErrorExplainer (xai)
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from ops_assistant.tools import project_ops
from ops_assistant.db.history_db import HistoryDatabase
from ops_assistant.explainer.xai import CommandExplainer, ErrorExplainer
from ops_assistant.agent import OpsAssistantAgent, GeminiProvider
from ops_assistant.nlp.intent_router import IntentRouter, IntentType


class TestEnhancedFeatures(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test_history.db")
        self.hdb = HistoryDatabase(db_path=self.db_path)
        self.agent = OpsAssistantAgent()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_project_ops_detect_python(self):
        req_file = os.path.join(self.test_dir, "requirements.txt")
        with open(req_file, "w") as f:
            f.write("requests==2.31.0\n")
        
        info = project_ops.detect_project_type(self.test_dir)
        self.assertTrue(info["has_project"])
        self.assertEqual(info["language"], "python")
        self.assertEqual(info["manifest"], "requirements.txt")

    def test_project_ops_detect_nodejs(self):
        pkg_file = os.path.join(self.test_dir, "package.json")
        with open(pkg_file, "w") as f:
            f.write('{"name": "test-pkg", "dependencies": {}}\n')
        
        info = project_ops.detect_project_type(self.test_dir)
        self.assertTrue(info["has_project"])
        self.assertIn("node", info["language"])

    def test_project_ops_create_venv_dry_run(self):
        res = project_ops.create_python_venv(target_dir=self.test_dir, venv_name="myenv", dry_run=True)
        self.assertTrue(res["success"])
        self.assertIn("python3 -m venv", res["command"])

    def test_history_database_lifecycle(self):
        # Create session
        sid = self.hdb.create_session("Install dependencies", metadata={"mode": "cli"})
        self.assertTrue(bool(sid))

        # Log command
        cid = self.hdb.log_command(
            session_id=sid,
            query="install dependencies",
            command="pip install -r requirements.txt",
            intent="project_install_deps",
            safety_level="MODIFYING",
            risk_score=0.25,
            returncode=0,
            stdout="Successfully installed",
            stderr="",
            elapsed_ms=45.2
        )
        self.assertIsNotNone(cid)

        # Retrieve session history
        history = self.hdb.get_session_history(sid)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["command"], "pip install -r requirements.txt")

        # List sessions
        sessions = self.hdb.list_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["id"], sid)

        # Delete session
        self.hdb.delete_session(sid)
        self.assertEqual(len(self.hdb.list_sessions()), 0)

    def test_command_explainer(self):
        exp = CommandExplainer.explain("tar -czvf backup.tar.gz /etc")
        self.assertEqual(exp["base_command"], "tar")
        self.assertTrue(len(exp["flags_detected"]) > 0)
        self.assertIn("tar", exp["summary"])

    def test_error_explainer(self):
        err = ErrorExplainer.explain("open browser", returncode=127, stderr="/bin/sh: line 1: open: command not found")
        self.assertEqual(err["error_class"], "COMMAND_NOT_FOUND")
        self.assertIn("xdg-open", err["recommendation"])

    def test_intent_router_new_intents(self):
        router = IntentRouter()
        
        # Browser
        i1 = router.classify("open browser")
        self.assertEqual(i1.type, IntentType.DESKTOP_OPEN_BROWSER)

        # Explain
        i2 = router.classify("explain command tar -czf archive.tar.gz /data")
        self.assertEqual(i2.type, IntentType.COMMAND_EXPLAIN)

        # Project dependencies
        i3 = router.classify("install project dependencies")
        self.assertEqual(i3.type, IntentType.PROJECT_INSTALL_DEPS)

        # Create venv
        i4 = router.classify("create a python virtual environment named myenv")
        self.assertEqual(i4.type, IntentType.PROJECT_CREATE_VENV)
        self.assertEqual(i4.args.get("venv_name"), "myenv")

        # Trash clean
        i5 = router.classify("clean my trash")
        self.assertEqual(i5.type, IntentType.STORAGE_CLEAN_TRASH)

        # CPU check
        i6 = router.classify("check my cpu usage")
        self.assertEqual(i6.type, IntentType.SYSTEM_CHECK_CPU)


if __name__ == "__main__":
    unittest.main()
