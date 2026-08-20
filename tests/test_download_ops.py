"""Unit tests for Universal Stream Downloader and Extractor."""

import unittest
import tempfile
import os
import shutil
import zipfile
from unittest.mock import patch, MagicMock
from io import BytesIO

from ops_assistant.tools import download_ops


class TestDownloadOps(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="ops_test_download_")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    @patch("urllib.request.urlopen")
    def test_download_file_plain(self, mock_urlopen):
        fake_content = b"Hello, Linux Ops Assistant Downloader!"
        mock_response = MagicMock()
        mock_response.read.side_effect = [fake_content, b""]
        mock_response.headers = {"Content-Length": str(len(fake_content))}
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        res = download_ops.download_file("https://example.com/data.txt", destination_dir=self.test_dir)
        self.assertTrue(res["success"])
        self.assertEqual(res["size_bytes"], len(fake_content))
        self.assertTrue(os.path.exists(res["file_path"]))

        with open(res["file_path"], "rb") as f:
            self.assertEqual(f.read(), fake_content)

    def test_extract_zip_archive(self):
        # Create a test zip file
        zip_path = os.path.join(self.test_dir, "archive.zip")
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("inner_file.txt", "extracted successfully")

        ext_res = download_ops.extract_archive(zip_path, self.test_dir)
        self.assertTrue(ext_res["success"])
        self.assertTrue(os.path.exists(os.path.join(self.test_dir, "inner_file.txt")))


if __name__ == "__main__":
    unittest.main()