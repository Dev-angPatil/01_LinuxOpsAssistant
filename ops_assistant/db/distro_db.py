"""Embedded SQLite Distro Knowledge Base for multi-distribution Linux operations."""

import os
import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional

DEFAULT_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "distro_knowledge.json"
DEFAULT_DB_PATH = Path.home() / ".config" / "ops_assistant" / "distro_knowledge.db"


class DistroKnowledgeBase:
    """Manages the embedded SQLite database of Linux distribution specifications."""

    def __init__(self, db_path: Optional[str] = None, data_source_path: Optional[str] = None):
        if db_path is None:
            self.db_path = str(DEFAULT_DB_PATH)
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        else:
            self.db_path = db_path
            if self.db_path != ":memory:":
                os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)

        self.data_source_path = str(data_source_path or DEFAULT_DATA_PATH)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self._profiles_cache: Dict[str, Dict[str, Any]] = {}
        self._commands_cache: Dict[Tuple[str, str, str], str] = {}
        self._all_families_cache: Optional[List[str]] = None
        self._init_schema()
        self._seed_if_empty()

    def _init_schema(self) -> None:
        """Creates the required relational tables if they do not exist."""
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS distro_profiles (
                family_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                os_release_ids TEXT NOT NULL,
                os_release_id_like TEXT NOT NULL,
                detection_file TEXT,
                init_system TEXT NOT NULL,
                default_firewall TEXT NOT NULL,
                security_subsystem TEXT NOT NULL,
                log_paths TEXT NOT NULL,
                network_config_paths TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS distro_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_id TEXT NOT NULL,
                category TEXT NOT NULL,
                action TEXT NOT NULL,
                command_template TEXT NOT NULL,
                FOREIGN KEY (family_id) REFERENCES distro_profiles(family_id),
                UNIQUE(family_id, category, action)
            );

            CREATE TABLE IF NOT EXISTS distro_locks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_id TEXT NOT NULL,
                lock_file TEXT NOT NULL,
                lock_processes TEXT NOT NULL,
                FOREIGN KEY (family_id) REFERENCES distro_profiles(family_id)
            );

            CREATE TABLE IF NOT EXISTS distro_error_signatures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                family_id TEXT NOT NULL,
                signature_id TEXT NOT NULL,
                pattern TEXT NOT NULL,
                remediation TEXT NOT NULL,
                explanation TEXT NOT NULL,
                FOREIGN KEY (family_id) REFERENCES distro_profiles(family_id),
                UNIQUE(family_id, signature_id)
            );
        """)
        self.conn.commit()

    def _seed_if_empty(self) -> None:
        """Seeds the database from JSON if the profiles table is empty."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM distro_profiles")
        count = cursor.fetchone()[0]
        if count == 0 and os.path.exists(self.data_source_path):
            self.seed_from_json(self.data_source_path)

    def seed_from_json(self, json_path: str) -> None:
        """Loads and populates tables from a structured JSON dataset."""
        self._profiles_cache.clear()
        self._commands_cache.clear()
        self._all_families_cache = None

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        families = data.get("families", {})
        cursor = self.conn.cursor()

        for fid, finfo in families.items():
            ident = finfo.get("identification", {})
            svc = finfo.get("service_manager", {})
            pkg = finfo.get("package_manager", {})
            fw = finfo.get("firewall", {})
            sec = finfo.get("security_subsystem", {})
            log_paths = finfo.get("log_paths", {})
            net_paths = finfo.get("network_config_paths", [])

            cursor.execute("""
                INSERT OR REPLACE INTO distro_profiles (
                    family_id, display_name, os_release_ids, os_release_id_like,
                    detection_file, init_system, default_firewall, security_subsystem,
                    log_paths, network_config_paths
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                fid,
                finfo.get("display_name", fid),
                json.dumps(ident.get("os_release_ids", [])),
                json.dumps(ident.get("os_release_id_like", [])),
                ident.get("detection_file"),
                finfo.get("init_system", "systemd"),
                fw.get("default_tool", "iptables"),
                sec.get("type", "none"),
                json.dumps(log_paths),
                json.dumps(net_paths)
            ))

            # Seed service manager commands
            for action, cmd in svc.get("commands", {}).items():
                cursor.execute("""
                    INSERT OR REPLACE INTO distro_commands (family_id, category, action, command_template)
                    VALUES (?, ?, ?, ?)
                """, (fid, "service", action, cmd))

            # Seed package manager commands
            for action, cmd in pkg.get("commands", {}).items():
                cursor.execute("""
                    INSERT OR REPLACE INTO distro_commands (family_id, category, action, command_template)
                    VALUES (?, ?, ?, ?)
                """, (fid, "package", action, cmd))

            # Seed firewall commands
            for action, cmd in fw.get("commands", {}).items():
                cursor.execute("""
                    INSERT OR REPLACE INTO distro_commands (family_id, category, action, command_template)
                    VALUES (?, ?, ?, ?)
                """, (fid, "firewall", action, cmd))

            # Seed security commands
            for action, cmd in sec.get("commands", {}).items():
                cursor.execute("""
                    INSERT OR REPLACE INTO distro_commands (family_id, category, action, command_template)
                    VALUES (?, ?, ?, ?)
                """, (fid, "security", action, cmd))

            # Seed lock files
            for lfile in pkg.get("lock_files", []):
                cursor.execute("""
                    INSERT INTO distro_locks (family_id, lock_file, lock_processes)
                    VALUES (?, ?, ?)
                """, (fid, lfile, json.dumps(pkg.get("lock_processes", []))))

            # Seed error signatures
            for sig in finfo.get("common_error_signatures", []):
                cursor.execute("""
                    INSERT OR REPLACE INTO distro_error_signatures (
                        family_id, signature_id, pattern, remediation, explanation
                    ) VALUES (?, ?, ?, ?, ?)
                """, (
                    fid,
                    sig.get("id", sig.get("pattern", "UNKNOWN")),
                    sig.get("pattern", ""),
                    sig.get("remediation", ""),
                    sig.get("explanation", "")
                ))

        self.conn.commit()

    def get_profile(self, family_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves profile configuration for a given distribution family with memory caching."""
        if family_id in self._profiles_cache:
            return self._profiles_cache[family_id]

        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM distro_profiles WHERE family_id = ?", (family_id,))
        row = cursor.fetchone()
        if not row:
            return None
        profile = {
            "family_id": row["family_id"],
            "display_name": row["display_name"],
            "os_release_ids": json.loads(row["os_release_ids"]),
            "os_release_id_like": json.loads(row["os_release_id_like"]),
            "detection_file": row["detection_file"],
            "init_system": row["init_system"],
            "default_firewall": row["default_firewall"],
            "security_subsystem": row["security_subsystem"],
            "log_paths": json.loads(row["log_paths"]),
            "network_config_paths": json.loads(row["network_config_paths"])
        }
        self._profiles_cache[family_id] = profile
        return profile

    def get_all_families(self) -> List[str]:
        """Returns all supported distribution family IDs with memory caching."""
        if self._all_families_cache is not None:
            return self._all_families_cache

        cursor = self.conn.cursor()
        cursor.execute("SELECT family_id FROM distro_profiles")
        self._all_families_cache = [row[0] for row in cursor.fetchall()]
        return self._all_families_cache

    def get_command(
        self,
        family_id: str,
        category: str,
        action: str,
        **kwargs: Any
    ) -> Optional[str]:
        """Resolves a parameterized command template for a distro family with caching."""
        cache_key = (family_id, category, action)
        if cache_key in self._commands_cache:
            template = self._commands_cache[cache_key]
        else:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT command_template FROM distro_commands
                WHERE family_id = ? AND category = ? AND action = ?
            """, (family_id, category, action))
            row = cursor.fetchone()
            if not row:
                return None
            template = row[0]
            self._commands_cache[cache_key] = template

        if kwargs:
            try:
                return template.format(**kwargs)
            except KeyError:
                return template
        return template

    def get_locks(self, family_id: str) -> List[Dict[str, Any]]:
        """Returns all package manager lock files and competing processes for a distro."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT lock_file, lock_processes FROM distro_locks WHERE family_id = ?", (family_id,))
        rows = cursor.fetchall()
        return [
            {"lock_file": r[0], "lock_processes": json.loads(r[1])}
            for r in rows
        ]

    def get_error_signatures(self, family_id: str) -> List[Dict[str, Any]]:
        """Returns common error patterns and remediations for a distro family."""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT signature_id, pattern, remediation, explanation
            FROM distro_error_signatures WHERE family_id = ?
        """, (family_id,))
        rows = cursor.fetchall()
        return [
            {
                "id": r["signature_id"],
                "pattern": r["pattern"],
                "remediation": r["remediation"],
                "explanation": r["explanation"]
            }
            for r in rows
        ]

    def get_log_paths(self, family_id: str) -> Dict[str, str]:
        """Returns the dictionary of log paths for the distro family."""
        profile = self.get_profile(family_id)
        if profile:
            return profile.get("log_paths", {})
        return {
            "system": "/var/log/syslog",
            "auth": "/var/log/auth.log",
            "package_manager": "/var/log/dpkg.log",
            "kernel": "/var/log/kern.log"
        }

    def close(self) -> None:
        """Closes the underlying SQLite database connection."""
        self.conn.close()
