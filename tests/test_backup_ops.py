"""Unit tests for Backup and Restore Operations."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from ops_assistant.tools import backup_ops


class TestBackupOps(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="ops_test_backup_")
        self.source_dir = os.path.join(self.temp_dir, "test_config")
        self.backup_dir = os.path.join(self.temp_dir, "stored_backups")
        os.makedirs(self.source_dir, exist_ok=True)
        os.makedirs(self.backup_dir, exist_ok=True)

        with open(os.path.join(self.source_dir, "nginx.conf"), "w") as f:
            f.write("server { listen 80; }\n")

    def tearDown(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_create_and_list_backup(self):
        res = backup_ops.create_backup(self.source_dir, backup_dir=self.backup_dir, prefix="test_snap")
        self.assertTrue(res["success"])
        self.assertTrue(os.path.exists(res["backup_file"]))
        self.assertIn("rollback_command", res)

        list_res = backup_ops.list_backups(self.backup_dir)
        self.assertTrue(list_res["success"])
        self.assertEqual(list_res["count"], 1)
        self.assertEqual(list_res["backups"][0]["full_path"], res["backup_file"])

    def test_verify_backup_valid(self):
        res = backup_ops.create_backup(self.source_dir, backup_dir=self.backup_dir)
        bfile = res["backup_file"]

        verify_res = backup_ops.verify_backup(bfile)
        self.assertTrue(verify_res["success"])
        self.assertTrue(verify_res["valid"])
        self.assertGreaterEqual(verify_res["file_count"], 1)

    def test_verify_backup_invalid(self):
        corrupt_file = os.path.join(self.backup_dir, "corrupt.tar.gz")
        with open(corrupt_file, "wb") as f:
            f.write(b"NOT_A_TAR_GZ_FILE")

        verify_res = backup_ops.verify_backup(corrupt_file)
        self.assertFalse(verify_res["success"])
        self.assertFalse(verify_res["valid"])

    def test_restore_backup(self):
        res = backup_ops.create_backup(self.source_dir, backup_dir=self.backup_dir)
        bfile = res["backup_file"]

        restore_dst = os.path.join(self.temp_dir, "restored_dir")
        restore_res = backup_ops.restore_backup(bfile, destination_dir=restore_dst, create_safety_copy=False)
        self.assertTrue(restore_res["success"])
        self.assertTrue(os.path.exists(os.path.join(restore_dst, "test_config", "nginx.conf")))


if __name__ == "__main__":
    unittest.main()
