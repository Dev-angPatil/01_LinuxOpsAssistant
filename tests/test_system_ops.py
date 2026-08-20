"""Unit tests for System Maintenance, Crontab Automation & Boot Analysis."""

import unittest
from unittest.mock import patch, MagicMock
from ops_assistant.tools import system_ops


class TestSystemOps(unittest.TestCase):
    @patch("ops_assistant.tools.system_ops._run_cmd")
    def test_list_cron_jobs(self, mock_run):
        mock_run.return_value = (0, "# Comment\n0 2 * * * /usr/local/bin/backup.sh\n30 4 * * 1 /usr/bin/certbot renew\n", "")
        res = system_ops.list_cron_jobs()
        self.assertTrue(res["success"])
        self.assertEqual(res["user_jobs_count"], 2)
        self.assertEqual(res["user_crontab_jobs"][0], "0 2 * * * /usr/local/bin/backup.sh")

    def test_add_cron_job_invalid_syntax(self):
        res = system_ops.add_cron_job("invalid_cron_syntax", "/bin/echo hi")
        self.assertFalse(res["success"])
        self.assertIn("Invalid cron schedule", res["error"])

    @patch("subprocess.run")
    @patch("ops_assistant.tools.system_ops._run_cmd")
    def test_add_cron_job_valid(self, mock_run_cmd, mock_subproc):
        mock_run_cmd.return_value = (0, "0 1 * * * /bin/old.sh\n", "")
        mock_subproc.return_value = MagicMock(returncode=0, stderr="")
        res = system_ops.add_cron_job("0 3 * * *", "/usr/bin/python3 script.py")
        self.assertTrue(res["success"])
        self.assertEqual(res["entry"], "0 3 * * * /usr/bin/python3 script.py")

    @patch("subprocess.run")
    @patch("ops_assistant.tools.system_ops._run_cmd")
    def test_remove_cron_job(self, mock_run_cmd, mock_subproc):
        mock_run_cmd.return_value = (0, "0 1 * * * /bin/old.sh\n0 3 * * * /bin/target.sh\n", "")
        mock_subproc.return_value = MagicMock(returncode=0, stderr="")
        res = system_ops.remove_cron_job("target.sh")
        self.assertTrue(res["success"])
        self.assertEqual(res["removed_count"], 1)

    @patch("shutil.which", return_value="/usr/bin/journalctl")
    @patch("ops_assistant.tools.system_ops._run_cmd")
    def test_vacuum_journal_dry_run(self, mock_run, mock_which):
        mock_run.return_value = (0, "Archived and active journals take up 1.2G in the file system.", "")
        res = system_ops.vacuum_journal(max_size="100M", dry_run=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])
        self.assertIn("--vacuum-size=100M", res["proposed_command"])

    @patch("shutil.which", return_value="/usr/bin/fstrim")
    def test_trim_ssds_dry_run(self, mock_which):
        res = system_ops.trim_ssds(dry_run=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])
        self.assertIn("fstrim", res["proposed_command"])

    @patch("shutil.which", return_value="/usr/bin/systemd-analyze")
    @patch("ops_assistant.tools.system_ops._run_cmd")
    def test_analyze_boot_time(self, mock_run, mock_which):
        def side_effect(cmd, **kwargs):
            if "time" in cmd:
                return (0, "Startup finished in 2.152s (kernel) + 4.218s (userspace) = 6.370s", "")
            elif "blame" in cmd:
                return (0, "1.821s NetworkManager.service\n952ms docker.service\n412ms ufw.service\n", "")
            return (0, "", "")

        mock_run.side_effect = side_effect
        res = system_ops.analyze_boot_time()
        self.assertTrue(res["success"])
        self.assertIn("6.370s", res["overall_boot_time"])
        self.assertEqual(len(res["top_slow_services"]), 3)
        self.assertEqual(res["top_slow_services"][0]["service"], "NetworkManager.service")

    @patch("shutil.which", return_value="/usr/bin/apt-get")
    def test_clean_package_cache_dry_run(self, mock_which):
        res = system_ops.clean_package_cache(dry_run=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])
        self.assertEqual(res["package_manager"], "apt")
        self.assertIn("apt-get clean", res["proposed_command"])


if __name__ == "__main__":
    unittest.main()
