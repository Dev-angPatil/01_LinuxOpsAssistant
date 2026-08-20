"""Unit tests for Docker and Container Operations."""

import unittest
from unittest.mock import patch
from ops_assistant.tools import docker_ops


class TestDockerOps(unittest.TestCase):
    @patch("ops_assistant.tools.docker_ops._docker_available", return_value=False)
    def test_docker_unavailable(self, mock_avail):
        res = docker_ops.list_containers()
        self.assertFalse(res["success"])
        self.assertEqual(res["count"], 0)

        res_logs = docker_ops.get_container_logs("my_container")
        self.assertFalse(res_logs["success"])

        res_restart = docker_ops.restart_container("my_container")
        self.assertFalse(res_restart["success"])

    @patch("ops_assistant.tools.docker_ops._run_docker")
    @patch("ops_assistant.tools.docker_ops._docker_available", return_value=True)
    def test_list_containers_mock(self, mock_avail, mock_run):
        mock_output = (
            '{"ID":"abc123456789","Image":"nginx:alpine","Status":"Up 2 hours","State":"running","Names":"web-app","Ports":"0.0.0.0:80->80/tcp"}\n'
            '{"ID":"def987654321","Image":"postgres:15","Status":"Exited (1) 10 minutes ago","State":"exited","Names":"db-postgres","Ports":""}'
        )
        mock_run.return_value = (0, mock_output, "")

        res = docker_ops.list_containers()
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 2)
        self.assertEqual(res["running_count"], 1)
        self.assertEqual(res["failed_count"], 1)
        self.assertEqual(res["containers"][0]["names"], "web-app")

    @patch("ops_assistant.tools.docker_ops._run_docker")
    @patch("ops_assistant.tools.docker_ops._docker_available", return_value=True)
    def test_restart_container_mock(self, mock_avail, mock_run):
        mock_run.return_value = (0, "web-app", "")
        res = docker_ops.restart_container("web-app")
        self.assertTrue(res["success"])
        self.assertIn("Successfully restarted", res["message"])
        self.assertEqual(res["rollback_command"], "docker stop 'web-app'")

    @patch("ops_assistant.tools.docker_ops._run_docker")
    @patch("ops_assistant.tools.docker_ops._docker_available", return_value=True)
    def test_prune_docker_dry_run(self, mock_avail, mock_run):
        mock_df = '{"Type":"Images","TotalCount":"5","Active":"2","Size":"1.2GB","Reclaimable":"600MB (50%)"}'
        mock_run.return_value = (0, mock_df, "")
        res = docker_ops.prune_docker_resources(dry_run=True)
        self.assertTrue(res["success"])
        self.assertTrue(res["dry_run"])
        self.assertIn("docker system prune -f", res["proposed_command"])

    @patch("ops_assistant.tools.docker_ops.list_containers")
    def test_inspect_container_conflicts(self, mock_list):
        mock_list.return_value = {
            "success": True,
            "count": 2,
            "containers": [
                {"id": "c1", "names": "web-1", "status": "Up 1 hour", "ports": "0.0.0.0:8080->80/tcp"},
                {"id": "c2", "names": "web-2", "status": "Exited (1) 5m ago", "ports": "0.0.0.0:8080->80/tcp"}
            ]
        }
        res = docker_ops.inspect_container_conflicts()
        self.assertEqual(len(res["crashed_containers"]), 1)
        self.assertEqual(res["crashed_containers"][0]["names"], "web-2")
        self.assertEqual(len(res["conflicts"]), 1)
        self.assertEqual(res["conflicts"][0]["port"], "8080")


if __name__ == "__main__":
    unittest.main()
