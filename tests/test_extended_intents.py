"""Unit tests for Extended NLP Intent Routing (Desktop, Download, Files)."""

import unittest
from ops_assistant.nlp.intent_router import IntentRouter, IntentType


class TestExtendedIntents(unittest.TestCase):
    def setUp(self):
        self.router = IntentRouter()

    def test_desktop_open_folder(self):
        cases = [
            ("open folder ~/Downloads", "~/Downloads"),
            ("open directory /var/log", "/var/log"),
            ("open folder pictures", "pictures"),
        ]
        for query, expected_path in cases:
            intent = self.router.classify(query)
            self.assertEqual(intent.type, IntentType.DESKTOP_OPEN_FOLDER, f"Failed for query: {query}")
            self.assertEqual(intent.args.get("path"), expected_path)

    def test_desktop_open_browser(self):
        cases = [
            ("open browser https://google.com", "https://google.com"),
            ("open url https://github.com", "https://github.com"),
            ("browse to http://localhost:8080", "http://localhost:8080"),
        ]
        for query, expected_url in cases:
            intent = self.router.classify(query)
            self.assertEqual(intent.type, IntentType.DESKTOP_OPEN_BROWSER, f"Failed for query: {query}")
            self.assertEqual(intent.args.get("url"), expected_url)

    def test_download_url(self):
        cases = [
            ("download https://example.com/archive.zip", "https://example.com/archive.zip"),
            ("fetch url https://domain.com/file.tar.gz to ~/Downloads", "https://domain.com/file.tar.gz"),
        ]
        for query, expected_url in cases:
            intent = self.router.classify(query)
            self.assertEqual(intent.type, IntentType.DOWNLOAD_URL, f"Failed for query: {query}")
            self.assertEqual(intent.args.get("url"), expected_url)

    def test_file_move_and_copy_and_trash(self):
        m_intent = self.router.classify("move /tmp/a.txt to /tmp/b.txt")
        self.assertEqual(m_intent.type, IntentType.FILE_MOVE)
        self.assertEqual(m_intent.args.get("src"), "/tmp/a.txt")
        self.assertEqual(m_intent.args.get("dst"), "/tmp/b.txt")

        c_intent = self.router.classify("copy file1.txt to file2.txt")
        self.assertEqual(c_intent.type, IntentType.FILE_COPY)
        self.assertEqual(c_intent.args.get("src"), "file1.txt")
        self.assertEqual(c_intent.args.get("dst"), "file2.txt")

        t_intent = self.router.classify("trash /tmp/junk.log")
        self.assertEqual(t_intent.type, IntentType.FILE_TRASH)
        self.assertEqual(t_intent.args.get("path"), "/tmp/junk.log")

    def test_hardware_and_tuning_intents(self):
        h1 = self.router.classify("check my hardware specs and gpu")
        self.assertEqual(h1.type, IntentType.HARDWARE_PROFILE)

        h2 = self.router.classify("which ai model should i download for my gpu and ram?")
        self.assertEqual(h2.type, IntentType.HARDWARE_RECOMMEND_MODEL)

        h3 = self.router.classify("auto tune system capabilities for my hardware")
        self.assertEqual(h3.type, IntentType.HARDWARE_AUTO_TUNE)

    def test_proactive_health_intent(self):
        p1 = self.router.classify("run a proactive health audit on my system")
        self.assertEqual(p1.type, IntentType.PROACTIVE_AUDIT)

        p2 = self.router.classify("scan system for bottlenecks and risks")
        self.assertEqual(p2.type, IntentType.PROACTIVE_AUDIT)

    def test_docker_intents(self):
        d1 = self.router.classify("list all docker containers")
        self.assertEqual(d1.type, IntentType.DOCKER_LIST)

        d2 = self.router.classify("show docker logs for web-app")
        self.assertEqual(d2.type, IntentType.DOCKER_LOGS)
        self.assertEqual(d2.args.get("container"), "web-app")

        d3 = self.router.classify("restart container nginx_proxy")
        self.assertEqual(d3.type, IntentType.DOCKER_RESTART)
        self.assertEqual(d3.args.get("container"), "nginx_proxy")

        d4 = self.router.classify("prune unused docker containers and images")
        self.assertEqual(d4.type, IntentType.DOCKER_PRUNE)

    def test_system_maintenance_intents(self):
        c1 = self.router.classify("list my scheduled cron jobs")
        self.assertEqual(c1.type, IntentType.CRON_LIST)

        b1 = self.router.classify("analyze boot time and slow services")
        self.assertEqual(b1.type, IntentType.SYSTEM_BOOT_ANALYSIS)

        t1 = self.router.classify("trim ssd filesystems")
        self.assertEqual(t1.type, IntentType.SYSTEM_TRIM_SSD)

        p1 = self.router.classify("clean apt package cache")
        self.assertEqual(p1.type, IntentType.SYSTEM_PACKAGE_CLEAN)

        j1 = self.router.classify("vacuum systemd journal logs")
        self.assertEqual(j1.type, IntentType.SYSTEM_JOURNAL_VACUUM)

    def test_security_intents(self):
        s1 = self.router.classify("run a security audit on this server")
        self.assertEqual(s1.type, IntentType.SECURITY_AUDIT)

        s2 = self.router.classify("check ssh security configuration")
        self.assertEqual(s2.type, IntentType.SECURITY_SSH_CHECK)

        s3 = self.router.classify("check for ssh brute force attacks")
        self.assertEqual(s3.type, IntentType.SECURITY_BRUTEFORCE)

        s4 = self.router.classify("scan for suid binaries and privilege escalation")
        self.assertEqual(s4.type, IntentType.SECURITY_SUID)

    def test_backup_intents(self):
        b1 = self.router.classify("backup /etc/nginx configuration")
        self.assertEqual(b1.type, IntentType.BACKUP_CREATE)
        self.assertEqual(b1.args.get("path"), "/etc/nginx")

        b2 = self.router.classify("list saved backups")
        self.assertEqual(b2.type, IntentType.BACKUP_LIST)

        b3 = self.router.classify("restore backup backup.tar.gz to /etc")
        self.assertEqual(b3.type, IntentType.BACKUP_RESTORE)


if __name__ == "__main__":
    unittest.main()