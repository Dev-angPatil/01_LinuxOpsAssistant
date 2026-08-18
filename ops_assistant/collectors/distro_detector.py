"""Linux Distribution Detector parsing /etc/os-release and system identifiers."""

import os
import re
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from ops_assistant.db.distro_db import DistroKnowledgeBase


@dataclass
class DistroInfo:
    family_id: str
    distro_id: str
    distro_name: str
    version_id: str
    id_like: List[str] = field(default_factory=list)
    init_system: str = "systemd"
    package_manager: str = "apt"
    default_firewall: str = "ufw"
    security_subsystem: str = "apparmor"
    is_simulated: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "family_id": self.family_id,
            "distro_id": self.distro_id,
            "distro_name": self.distro_name,
            "version_id": self.version_id,
            "id_like": self.id_like,
            "init_system": self.init_system,
            "package_manager": self.package_manager,
            "default_firewall": self.default_firewall,
            "security_subsystem": self.security_subsystem,
            "is_simulated": self.is_simulated
        }


class DistroDetector:
    """Detects the host Linux distribution and resolves its canonical family."""

    KNOWN_FALLBACKS = [
        ("/etc/debian_version", "debian"),
        ("/etc/redhat-release", "rhel"),
        ("/etc/arch-release", "arch"),
        ("/etc/alpine-release", "alpine"),
        ("/etc/SuSE-release", "suse")
    ]

    def __init__(self, db: Optional[DistroKnowledgeBase] = None, os_release_path: Optional[str] = None):
        self.db = db or DistroKnowledgeBase()
        self.os_release_path = os_release_path or self._find_os_release()
        self._cached_host_distro: Optional[DistroInfo] = None

    def _find_os_release(self) -> str:
        for path in ["/etc/os-release", "/usr/lib/os-release"]:
            if os.path.exists(path):
                return path
        return "/etc/os-release"

    def parse_os_release_content(self, content: str) -> Dict[str, str]:
        """Parses KEY=VALUE pairs from os-release format."""
        data: Dict[str, str] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("\"'")
                data[key] = val
        return data

    def detect(self, override_family: Optional[str] = None) -> DistroInfo:
        """Detects current host distribution and matches against DistroKnowledgeBase with caching."""
        if override_family:
            return self._build_from_family_id(override_family.lower(), is_simulated=True)

        if self._cached_host_distro is not None:
            return self._cached_host_distro

        os_data: Dict[str, str] = {}
        if os.path.exists(self.os_release_path):
            try:
                with open(self.os_release_path, "r", encoding="utf-8") as f:
                    os_data = self.parse_os_release_content(f.read())
            except Exception:
                pass

        distro_id = os_data.get("ID", "").lower()
        distro_name = os_data.get("PRETTY_NAME") or os_data.get("NAME") or distro_id or "Linux"
        version_id = os_data.get("VERSION_ID", "")
        id_like = [x.lower() for x in os_data.get("ID_LIKE", "").split() if x]

        family_id = self._resolve_family(distro_id, id_like)

        # If not resolved via os-release, check legacy files
        if not family_id:
            for filepath, fid in self.KNOWN_FALLBACKS:
                if os.path.exists(filepath):
                    family_id = fid
                    break

        if not family_id:
            family_id = "debian"  # Default canonical fallback

        res = self._build_from_family_id(
            family_id=family_id,
            distro_id=distro_id or family_id,
            distro_name=distro_name,
            version_id=version_id,
            id_like=id_like,
            is_simulated=False
        )
        self._cached_host_distro = res
        return res

    def _resolve_family(self, distro_id: str, id_like: List[str]) -> Optional[str]:
        """Maps a given distro_id and id_like list to a known family_id in the DB."""
        if not distro_id:
            return None

        all_families = self.db.get_all_families()

        # Check exact family_id match
        if distro_id in all_families:
            return distro_id

        # Query all profiles to check os_release_ids and os_release_id_like
        for fid in all_families:
            profile = self.db.get_profile(fid)
            if not profile:
                continue
            if distro_id in profile.get("os_release_ids", []):
                return fid
            for like in id_like:
                if like in profile.get("os_release_id_like", []):
                    return fid

        return None

    def _build_from_family_id(
        self,
        family_id: str,
        distro_id: Optional[str] = None,
        distro_name: Optional[str] = None,
        version_id: str = "",
        id_like: Optional[List[str]] = None,
        is_simulated: bool = False
    ) -> DistroInfo:
        """Constructs a DistroInfo object populated with database knowledge."""
        profile = self.db.get_profile(family_id) or self.db.get_profile("debian") or {}
        
        pkg_mgr_cmd = self.db.get_command(family_id, "package", "install") or "apt-get install"
        primary_pkg = "apt"
        if "dnf" in pkg_mgr_cmd:
            primary_pkg = "dnf"
        elif "pacman" in pkg_mgr_cmd:
            primary_pkg = "pacman"
        elif "apk" in pkg_mgr_cmd:
            primary_pkg = "apk"
        elif "zypper" in pkg_mgr_cmd:
            primary_pkg = "zypper"

        return DistroInfo(
            family_id=family_id,
            distro_id=distro_id or family_id,
            distro_name=distro_name or profile.get("display_name", family_id.title()),
            version_id=version_id,
            id_like=id_like or profile.get("os_release_id_like", []),
            init_system=profile.get("init_system", "systemd"),
            package_manager=primary_pkg,
            default_firewall=profile.get("default_firewall", "ufw"),
            security_subsystem=profile.get("security_subsystem", "apparmor"),
            is_simulated=is_simulated
        )
