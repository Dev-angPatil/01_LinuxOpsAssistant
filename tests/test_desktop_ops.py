"""Unit tests for Desktop and File Manipulation Operations."""

import unittest
import tempfile
import os
import shutil
from unittest.mock import patch, MagicMock

from ops_assistant.tools import desktop_ops


class TestDesktopOps(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ops_test_desktop_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch("subprocess.Popen")
    @patch("shutil.which")
    def test_open_folder(self, mock_which, mock_popen):
        mock_which.return_value = "/usr/bin/xdg-open"
        res = desktop_ops.open_folder(self.test_dir)
        self.assertTrue(res["success"])
        self.assertIn("Opened directory", res["message"])
    def test_open_folder_nonexistent(self):
        res = desktop_ops.open_folder("/non/existent/path/9999")
        self.assertFalse(res["success"])
        self.assertIn("error", res)

    @patch("subprocess.Popen")
    @patch("shutil.which")
    def test_open_file(self, mock_which, mock_popen):
        test_file = os.path.join(self.test_dir, "sample.txt")
        with open(test_file, "w") as f:
            f.write("test content")
        mock_which.return_value = "/usr/bin/xdg-open"
        res = desktop_ops.open_file(test_file)
        self.assertTrue(res["success"])

    @patch("subprocess.Popen")
    @patch("shutil.which")
    def test_open_image(self, mock_which, mock_popen):
        test_img = os.path.join(self.test_dir, "photo.png")
        with open(test_img, "wb") as f:
            f.write(b"PNG_DATA")
        mock_which.return_value = "/usr/bin/xdg-open"
        res = desktop_ops.open_image(test_img)
        self.assertTrue(res["success"])

    @patch("webbrowser.open")
    def test_open_browser(self, mock_wb_open):
        mock_wb_open.return_value = True
        res = desktop_ops.open_browser("https://github.com")
        self.assertTrue(res["success"])
        mock_wb_open.assert_called_once_with("https://github.com", new=2)

    def test_move_and_copy_and_trash(self):
        src_file = os.path.join(self.test_dir, "original.txt")
        with open(src_file, "w") as f:
            f.write("important data")

        # Copy
        dst_copy = os.path.join(self.test_dir, "copy.txt")
        c_res = desktop_ops.copy_path(src_file, dst_copy)
        self.assertTrue(c_res["success"])
        self.assertTrue(os.path.exists(dst_copy))

        # Move
        dst_move = os.path.join(self.test_dir, "moved.txt")
        m_res = desktop_ops.move_path(src_file, dst_move)
        self.assertTrue(m_res["success"])
        self.assertFalse(os.path.exists(src_file))
        self.assertTrue(os.path.exists(dst_move))
        self.assertIn("rollback_command", m_res)

        # Trash
        t_res = desktop_ops.trash_path(dst_move)
        self.assertTrue(t_res["success"])
        self.assertFalse(os.path.exists(dst_move))


if __name__ == "__main__":
    unittest.main()