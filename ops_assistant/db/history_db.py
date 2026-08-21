"""
Persistent SQLite Command & Chat Session History Database.
Shares execution logs, XAI explanations, and session archives between CLI and Web GUI.
"""

from __future__ import annotations

import os
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def get_history_db_path() -> Path:
    config_dir = Path.home() / ".config" / "ops_assistant"
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "history.db"


class HistoryDatabase:
    """Manages persistent SQLite history for chat sessions and command executions."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            self.db_path = str(get_history_db_path())
        else:
            self.db_path = db_path

        if self.db_path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)

        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        cursor = self.conn.cursor()
        cursor.executescript("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                source TEXT NOT NULL DEFAULT 'gui'
            );

            CREATE TABLE IF NOT EXISTS command_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT,
                timestamp REAL NOT NULL,
                query TEXT NOT NULL,
                command TEXT NOT NULL,
                intent TEXT,
                safety_level TEXT NOT NULL,
                risk_score REAL NOT NULL,
                returncode INTEGER,
                stdout TEXT,
                stderr TEXT,
                elapsed_ms REAL,
                explanation TEXT,
                rollback_command TEXT,
                working_directory TEXT,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_cmd_session ON command_history(session_id);
            CREATE INDEX IF NOT EXISTS idx_cmd_timestamp ON command_history(timestamp DESC);
        """)
        self.conn.commit()

    def create_session(self, title: str = "New Chat", source: str = "gui", metadata: Optional[Dict[str, Any]] = None) -> str:
        session_id = str(uuid.uuid4())
        now = time.time()
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO chat_sessions (id, title, created_at, updated_at, source) VALUES (?, ?, ?, ?, ?)",
            (session_id, title[:100], now, now, source)
        )
        self.conn.commit()
        return session_id

    def update_session_title(self, session_id: str, title: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title[:100], time.time(), session_id)
        )
        self.conn.commit()

    def list_sessions(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, title, created_at, updated_at, source FROM chat_sessions ORDER BY updated_at DESC LIMIT ?",
            (limit,)
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def delete_session(self, session_id: str) -> bool:
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM chat_sessions WHERE id = ?", (session_id,))
        cursor.execute("DELETE FROM command_history WHERE session_id = ?", (session_id,))
        self.conn.commit()
        return True

    def log_command(
        self,
        query: str,
        command: str,
        safety_level: str = "READ_ONLY",
        risk_score: float = 0.05,
        session_id: Optional[str] = None,
        intent: Optional[str] = None,
        returncode: Optional[int] = 0,
        stdout: Optional[str] = "",
        stderr: Optional[str] = "",
        elapsed_ms: Optional[float] = 0.0,
        explanation: Optional[str] = "",
        rollback_command: Optional[str] = None,
        working_directory: Optional[str] = None
    ) -> int:
        now = time.time()
        wd = working_directory or os.getcwd()

        if session_id:
            # Ensure session exists or create it
            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM chat_sessions WHERE id = ?", (session_id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO chat_sessions (id, title, created_at, updated_at, source) VALUES (?, ?, ?, ?, ?)",
                    (session_id, query[:60] or "Chat Session", now, now, "gui")
                )
            else:
                cursor.execute("UPDATE chat_sessions SET updated_at = ? WHERE id = ?", (now, session_id))

        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO command_history (
                session_id, timestamp, query, command, intent, safety_level,
                risk_score, returncode, stdout, stderr, elapsed_ms,
                explanation, rollback_command, working_directory
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            session_id, now, query, command, intent, safety_level,
            risk_score, returncode, stdout, stderr, elapsed_ms,
            explanation, rollback_command, wd
        ))
        self.conn.commit()
        return cursor.lastrowid

    def get_session_history(self, session_id: str) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM command_history WHERE session_id = ? ORDER BY timestamp ASC",
            (session_id,)
        )
        return [dict(r) for r in cursor.fetchall()]

    def get_recent_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT * FROM command_history ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        )
        return [dict(r) for r in cursor.fetchall()]

    def clear_all(self):
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM command_history")
        cursor.execute("DELETE FROM chat_sessions")
        self.conn.commit()


# Global singleton instance
_history_db = HistoryDatabase()


def get_history_db() -> HistoryDatabase:
    return _history_db
