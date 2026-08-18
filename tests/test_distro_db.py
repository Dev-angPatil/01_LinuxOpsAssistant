"""Unit tests for Distro Knowledge Base, Distro Detector, and Multi-Distro Diagnostic Adaptation."""

import os
import tempfile
import unittest
from ops_assistant.db.distro_db import DistroKnowledgeBase
from ops_assistant.collectors.distro_detector import DistroDetector, DistroInfo
from ops_assistant.agent import OpsAssistantAgent
from ops_assistant.models import SafetyLevel


class TestDistroKnowledgeBase(unittest.TestCase):
    def setUp(self):
        self.db = DistroKnowledgeBase(db_path=":memory:")

    def tearDown(self):
        self.db.close()

    def test_database_initialization_and_seeding(self):
        families = self.db.get_all_families()
        self.assertEqual(set(families), {"debian", "rhel", "arch", "alpine", "suse"})

        # Verify profiles
        debian_prof = self.db.get_profile("debian")
        self.assertIsNotNone(debian_prof)
        self.assertEqual(debian_prof["display_name"], "Debian / Ubuntu Family")
        self.assertEqual(debian_prof["init_system"], "systemd")
        self.assertEqual(debian_prof["default_firewall"], "ufw")
        self.assertEqual(debian_prof["security_subsystem"], "apparmor")

        rhel_prof = self.db.get_profile("rhel")
        self.assertIsNotNone(rhel_prof)
        self.assertEqual(rhel_prof["default_firewall"], "firewalld")
        self.assertEqual(rhel_prof["security_subsystem"], "selinux")

        alpine_prof = self.db.get_profile("alpine")
        self.assertIsNotNone(alpine_prof)
        self.assertEqual(alpine_prof["init_system"], "openrc")

    def test_command_templating(self):
        # Debian install
        deb_cmd = self.db.get_command("debian", "package", "install", package="nginx")
        self.assertIn("apt-get install -y nginx", deb_cmd)

        # RHEL install
        rhel_cmd = self.db.get_command("rhel", "package", "install", package="httpd")
        self.assertIn("dnf install -y httpd", rhel_cmd)

        # Arch install
        arch_cmd = self.db.get_command("arch", "package", "install", package="caddy")
        self.assertIn("pacman -S --noconfirm caddy", arch_cmd)

        # Alpine service start
        alp_cmd = self.db.get_command("alpine", "service", "start", service="nginx")
        self.assertEqual(alp_cmd, "sudo rc-service nginx start")

    def test_locks_and_error_signatures(self):
        # Locks
        deb_locks = self.db.get_locks("debian")
        self.assertTrue(any("/var/lib/dpkg/lock-frontend" in l["lock_file"] for l in deb_locks))

        arch_locks = self.db.get_locks("arch")
        self.assertTrue(any("/var/lib/pacman/db.lck" in l["lock_file"] for l in arch_locks))

        # Error signatures
        alp_sigs = self.db.get_error_signatures("alpine")
        self.assertTrue(any("APK_LOCK_BLOCKED" in s["id"] for s in alp_sigs))
        self.assertTrue(any("MUSL_GLIBC_MISSING" in s["id"] for s in alp_sigs))


class TestDistroDetector(unittest.TestCase):
    def setUp(self):
        self.db = DistroKnowledgeBase(db_path=":memory:")

    def tearDown(self):
        self.db.close()

    def test_parse_ubuntu_os_release(self):
        ubuntu_release = """
        NAME="Ubuntu"
        VERSION="22.04.4 LTS (Jammy Jellyfish)"
        ID=ubuntu
        ID_LIKE=debian
        PRETTY_NAME="Ubuntu 22.04.4 LTS"
        VERSION_ID="22.04"
        """
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(ubuntu_release)
            f_path = f.name

        try:
            detector = DistroDetector(db=self.db, os_release_path=f_path)
            info = detector.detect()
            self.assertEqual(info.family_id, "debian")
            self.assertEqual(info.distro_id, "ubuntu")
            self.assertEqual(info.package_manager, "apt")
            self.assertEqual(info.init_system, "systemd")
            self.assertEqual(info.default_firewall, "ufw")
        finally:
            if os.path.exists(f_path):
                os.unlink(f_path)

    def test_parse_rocky_os_release(self):
        rocky_release = """
        NAME="Rocky Linux"
        ID="rocky"
        ID_LIKE="rhel centos fedora"
        VERSION_ID="9.3"
        PRETTY_NAME="Rocky Linux 9.3"
        """
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(rocky_release)
            f_path = f.name

        try:
            detector = DistroDetector(db=self.db, os_release_path=f_path)
            info = detector.detect()
            self.assertEqual(info.family_id, "rhel")
            self.assertEqual(info.distro_id, "rocky")
            self.assertEqual(info.package_manager, "dnf")
            self.assertEqual(info.default_firewall, "firewalld")
            self.assertEqual(info.security_subsystem, "selinux")
        finally:
            if os.path.exists(f_path):
                os.unlink(f_path)

    def test_parse_arch_os_release(self):
        arch_release = """
        NAME="Arch Linux"
        PRETTY_NAME="Arch Linux"
        ID=arch
        """
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(arch_release)
            f_path = f.name

        try:
            detector = DistroDetector(db=self.db, os_release_path=f_path)
            info = detector.detect()
            self.assertEqual(info.family_id, "arch")
            self.assertEqual(info.package_manager, "pacman")
        finally:
            if os.path.exists(f_path):
                os.unlink(f_path)

    def test_parse_alpine_os_release(self):
        alpine_release = """
        NAME="Alpine Linux"
        ID=alpine
        VERSION_ID=3.19.1
        PRETTY_NAME="Alpine Linux v3.19"
        """
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write(alpine_release)
            f_path = f.name

        try:
            detector = DistroDetector(db=self.db, os_release_path=f_path)
            info = detector.detect()
            self.assertEqual(info.family_id, "alpine")
            self.assertEqual(info.init_system, "openrc")
            self.assertEqual(info.package_manager, "apk")
        finally:
            if os.path.exists(f_path):
                os.unlink(f_path)


class TestAgentDistroAdaptation(unittest.TestCase):
    def setUp(self):
        self.db = DistroKnowledgeBase(db_path=":memory:")
        self.detector = DistroDetector(db=self.db)
        self.agent = OpsAssistantAgent(distro_db=self.db, distro_detector=self.detector)

    def tearDown(self):
        self.db.close()

    def test_dpkg_lock_adaptation_across_distros(self):
        query = "apt-get upgrade failed: Could not get lock /var/lib/dpkg/lock-frontend"

        # Debian
        rep_deb = self.agent.diagnose(query, distro_override="debian")
        cmds_deb = [c.command for c in rep_deb.explanation.proposed_commands]
        self.assertTrue(any("dpkg --configure -a" in c for c in cmds_deb))

        # RHEL
        rep_rhel = self.agent.diagnose(query, distro_override="rhel")
        cmds_rhel = [c.command for c in rep_rhel.explanation.proposed_commands]
        self.assertTrue(any("rpm --rebuilddb" in c for c in cmds_rhel))
        self.assertTrue(any("dnf.pid" in c for c in cmds_rhel))

        # Arch
        rep_arch = self.agent.diagnose(query, distro_override="arch")
        cmds_arch = [c.command for c in rep_arch.explanation.proposed_commands]
        self.assertTrue(any("db.lck" in c for c in cmds_arch))
        self.assertTrue(any("archlinux-keyring" in c for c in cmds_arch))

        # Alpine
        rep_alp = self.agent.diagnose(query, distro_override="alpine")
        cmds_alp = [c.command for c in rep_alp.explanation.proposed_commands]
        self.assertTrue(any("apk" in c for c in cmds_alp))

        # openSUSE
        rep_suse = self.agent.diagnose(query, distro_override="suse")
        cmds_suse = [c.command for c in rep_suse.explanation.proposed_commands]
        self.assertTrue(any("zypper" in c or "packagekit" in c for c in cmds_suse))

    def test_firewall_adaptation_across_distros(self):
        query = "Traffic to port 80 is being dropped: UFW BLOCK Connection refused"

        # Debian / Ubuntu (ufw)
        rep_deb = self.agent.diagnose(query, distro_override="debian")
        cmds_deb = [c.command for c in rep_deb.explanation.proposed_commands]
        self.assertTrue(any("ufw status" in c for c in cmds_deb))

        # RHEL (firewalld)
        rep_rhel = self.agent.diagnose(query, distro_override="rhel")
        cmds_rhel = [c.command for c in rep_rhel.explanation.proposed_commands]
        self.assertTrue(any("firewall-cmd" in c for c in cmds_rhel))

        # Arch (nftables)
        rep_arch = self.agent.diagnose(query, distro_override="arch")
        cmds_arch = [c.command for c in rep_arch.explanation.proposed_commands]
        self.assertTrue(any("nft" in c for c in cmds_arch))

        # Alpine (awall)
        rep_alp = self.agent.diagnose(query, distro_override="alpine")
        cmds_alp = [c.command for c in rep_alp.explanation.proposed_commands]
        self.assertTrue(any("awall" in c for c in cmds_alp))

    def test_alpine_openrc_service_translation(self):
        query = "Why is nginx failing to start? (Unclassified anomaly)"
        rep_alp = self.agent.diagnose(query, distro_override="alpine")
        cmds_alp = [c.command for c in rep_alp.explanation.proposed_commands]
        self.assertTrue(any("rc-service nginx status" in c for c in cmds_alp))
        self.assertTrue(any("logread" in c for c in cmds_alp))
        self.assertFalse(any("systemctl" in c for c in cmds_alp))


if __name__ == "__main__":
    unittest.main()
