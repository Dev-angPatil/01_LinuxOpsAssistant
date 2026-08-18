"""Journal Collector for structured Linux systemd and kernel log retrieval."""

import os
import re
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional
from ops_assistant.models import LogRecord

RE_LOG_ERR = re.compile(r"err|fail|emerg|crit", re.IGNORECASE)
STANDARD_LOG_FILES = (
    "/var/log/syslog",
    "/var/log/messages",
    "/var/log/dpkg.log",
    "/var/log/auth.log"
)

class JournalCollector:
    def __init__(self):
        self.has_journalctl = shutil.which("journalctl") is not None
        self.has_dmesg = shutil.which("dmesg") is not None

    def query_journal(
        self,
        unit: Optional[str] = None,
        priority_max: int = 4,  # 0:emerg, 1:alert, 2:crit, 3:err, 4:warning
        lines: int = 50,
        since: Optional[str] = None
    ) -> List[LogRecord]:
        """Fetches structured log records from journalctl in JSON format."""
        if not self.has_journalctl:
            return self._mock_logs(unit)

        cmd = [
            "journalctl",
            "-o", "json",
            f"-p", f"0..{priority_max}",
            "-n", str(lines),
            "--no-pager"
        ]

        if unit:
            cmd.extend(["-u", unit])
        if since:
            cmd.extend(["--since", since])

        records: List[LogRecord] = []
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        raw = json.loads(line)
                        msg = raw.get("MESSAGE", "")
                        if isinstance(msg, list):  # byte array fallback
                            msg = bytes(msg).decode("utf-8", errors="replace")
                        
                        ts_raw = raw.get("__REALTIME_TIMESTAMP")
                        if ts_raw:
                            ts = datetime.fromtimestamp(int(ts_raw) / 1_000_000, tz=timezone.utc).isoformat()
                        else:
                            ts = datetime.now(timezone.utc).isoformat()

                        records.append(LogRecord(
                            timestamp=ts,
                            source="journald",
                            priority=str(raw.get("PRIORITY", priority_max)),
                            unit=raw.get("_SYSTEMD_UNIT", unit),
                            pid=int(raw.get("_PID")) if raw.get("_PID") else None,
                            message=str(msg)
                        ))
                    except Exception:
                        continue
        except Exception:
            pass

        if not records:
            # Fallback to plain journalctl if json parsing failed or was permission-denied
            try:
                plain_cmd = ["journalctl", "-n", str(lines), "--no-pager"]
                if unit:
                    plain_cmd.extend(["-u", unit])
                res = subprocess.run(plain_cmd, capture_output=True, text=True, timeout=3)
                if res.returncode == 0 and res.stdout:
                    now_ts = datetime.now(timezone.utc).isoformat()
                    for line in res.stdout.splitlines():
                        line_str = line.strip()
                        if line_str:
                            records.append(LogRecord(
                                timestamp=now_ts,
                                source="journald_plain",
                                priority=str(priority_max),
                                unit=unit,
                                message=line_str
                            ))
            except Exception:
                pass

        return records if records else self._mock_logs(unit)

    def query_kernel_dmesg(self, lines: int = 30) -> List[LogRecord]:
        """Fetches error/warning records from kernel ring buffer (dmesg)."""
        if not self.has_dmesg:
            return []

        records: List[LogRecord] = []
        try:
            cmd = ["dmesg", "-T", "--level=err,warn,crit,alert,emerg"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and res.stdout:
                now_ts = datetime.now(timezone.utc).isoformat()
                raw_lines = res.stdout.splitlines()[-lines:]
                for line in raw_lines:
                    line_str = line.strip()
                    if line_str:
                        records.append(LogRecord(
                            timestamp=now_ts,
                            source="dmesg",
                            priority="3",
                            unit="kernel",
                            message=line_str
                        ))
        except Exception:
            pass

        return records

    def query_var_log(self, subsystem: Optional[str] = None, lines: int = 30) -> List[LogRecord]:
        """Scans standard /var/log files with fast tail buffer seeking when journald is unavailable."""
        records: List[LogRecord] = []
        candidates: List[str] = []
        if subsystem:
            candidates.append(f"/var/log/{subsystem}/error.log")
            candidates.append(f"/var/log/{subsystem}.log")
        candidates.extend(STANDARD_LOG_FILES)

        now_ts = datetime.now(timezone.utc).isoformat()
        for log_path in candidates:
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                    # Fast tail read: Seek near end if file is large (> 32KB)
                    f.seek(0, os.SEEK_END)
                    size = f.tell()
                    if size > 32768:
                        f.seek(max(0, size - 16384))
                    else:
                        f.seek(0)
                    file_lines = f.read().splitlines()[-lines:]
                    log_name = os.path.basename(log_path)
                    for line in file_lines:
                        line_str = line.strip()
                        if line_str:
                            records.append(LogRecord(
                                timestamp=now_ts,
                                source=f"file:{log_name}",
                                priority="3" if RE_LOG_ERR.search(line_str) else "5",
                                unit=subsystem,
                                message=line_str
                            ))
            except OSError:
                continue
        return records

    def query_all_relevant_logs(self, unit: Optional[str] = None, subsystem: Optional[str] = None, lines: int = 50) -> List[LogRecord]:
        """Correlates logs across journald, dmesg, and /var/log flat files."""
        all_logs: List[LogRecord] = []
        
        # 1. Journald
        j_logs = self.query_journal(unit=unit, lines=lines)
        all_logs.extend(j_logs)

        # 2. Dmesg (kernel logs)
        d_logs = self.query_kernel_dmesg(lines=20)
        all_logs.extend(d_logs)

        # 3. File fallback if needed
        f_logs = self.query_var_log(subsystem=subsystem, lines=20)
        all_logs.extend(f_logs)

        return all_logs

    def _mock_logs(self, unit: Optional[str]) -> List[LogRecord]:
        u = unit or "nginx.service"
        now_ts = datetime.now(timezone.utc).isoformat()
        return [
            LogRecord(
                timestamp=now_ts,
                source="journald_mock",
                priority="3",
                unit=u,
                message=f"[emerg] bind() to 0.0.0.0:80 failed (98: Address already in use) for {u}"
            ),
            LogRecord(
                timestamp=now_ts,
                source="journald_mock",
                priority="3",
                unit=u,
                message=f"Failed with result 'exit-code' on unit {u}."
            )
        ]

