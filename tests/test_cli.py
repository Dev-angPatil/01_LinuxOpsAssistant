"""Unit tests for CLI and formatting commands."""

import os
import sys
import tempfile
import unittest
import subprocess

class TestCLI(unittest.TestCase):
    def test_cli_help(self):
        res = subprocess.run([sys.executable, "-m", "ops_assistant.cli", "--help"], capture_output=True, text=True, cwd="/home/deu/Coding Repos/SSM/01_LinuxOpsAssistant")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Linux Operations Assistant", res.stdout)

    def test_cli_inspect_health(self):
        res = subprocess.run([sys.executable, "-m", "ops_assistant.cli", "--inspect-health"], capture_output=True, text=True, cwd="/home/deu/Coding Repos/SSM/01_LinuxOpsAssistant")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Linux Health Snapshot", res.stdout)

    def test_cli_diagnose_query(self):
        res = subprocess.run([sys.executable, "-m", "ops_assistant.cli", "Why is NGINX failing to start?"], capture_output=True, text=True, cwd="/home/deu/Coding Repos/SSM/01_LinuxOpsAssistant")
        self.assertEqual(res.returncode, 0)
        self.assertIn("XAI Diagnosis", res.stdout)

    def test_cli_benchmark(self):
        res = subprocess.run([sys.executable, "-m", "ops_assistant.cli", "--benchmark"], capture_output=True, text=True, cwd="/home/deu/Coding Repos/SSM/01_LinuxOpsAssistant")
        self.assertEqual(res.returncode, 0)
        self.assertIn("SUMMARY:", res.stdout)
        self.assertIn("Accuracy:", res.stdout)

    def test_cli_demo(self):
        res = subprocess.run([sys.executable, "-m", "ops_assistant.cli", "--demo"], capture_output=True, text=True, cwd="/home/deu/Coding Repos/SSM/01_LinuxOpsAssistant")
        self.assertEqual(res.returncode, 0)
        self.assertIn("Scenario 1:", res.stdout)
        self.assertIn("Demo completed successfully", res.stdout)

    def test_cli_exports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_file = os.path.join(tmpdir, "report.json")
            md_file = os.path.join(tmpdir, "report.md")

            res = subprocess.run(
                [sys.executable, "-m", "ops_assistant.cli", "Out of memory in worker", "--export-json", json_file, "--export-md", md_file],
                capture_output=True,
                text=True,
                cwd="/home/deu/Coding Repos/SSM/01_LinuxOpsAssistant"
            )
            self.assertEqual(res.returncode, 0)
            self.assertTrue(os.path.exists(json_file))
            self.assertTrue(os.path.exists(md_file))
            with open(json_file, "r") as f:
                self.assertIn("explanation", f.read())
            with open(md_file, "r") as f:
                self.assertIn("XAI Diagnostic Report", f.read())

if __name__ == "__main__":
    unittest.main()

