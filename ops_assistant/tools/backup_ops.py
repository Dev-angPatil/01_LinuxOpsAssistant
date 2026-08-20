"""Atomic Backup & Configuration Snapshot Operations.

Creates timestamped compressed archives of critical system configs and directories,
verifies archive integrity, and executes safe restores with automated rollback backups.
"""

from __future__ import annotations

import os
import time
import shutil
import tarfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _expand_path(raw_path: str) -> Path:
    return Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()


def _format_size(nbytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024.0:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return f"{nbytes:.1f} TB"


def create_backup(
    target_path: str,
    backup_dir: str = "~/.ops_assistant/backups",
    prefix: str = "config_snapshot"
) -> Dict[str, Any]:
    """Create a compressed .tar.gz snapshot of target directory or file."""
    src = _expand_path(target_path)
    if not src.exists():
        return {"success": False, "error": f"Source path does not exist: {src}"}

    dst_dir = _expand_path(backup_dir)
    dst_dir.mkdir(parents=True, exist_ok=True)

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    sanitized_name = src.name.replace("/", "_").strip("_") or "root"
    archive_name = f"{prefix}_{sanitized_name}_{timestamp_str}.tar.gz"
    archive_path = dst_dir / archive_name

    try:
        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(src, arcname=src.name)

        size_bytes = archive_path.stat().st_size
        return {
            "success": True,
            "source_path": str(src),
            "backup_file": str(archive_path),
            "size_bytes": size_bytes,
            "size_human": _format_size(size_bytes),
            "timestamp": timestamp_str,
            "message": f"Successfully created snapshot at: {archive_path}",
            "rollback_command": f"rm -f '{archive_path}'"
        }
    except Exception as e:
        if archive_path.exists():
            archive_path.unlink()
        return {"success": False, "error": str(e), "source_path": str(src)}


def list_backups(backup_dir: str = "~/.ops_assistant/backups") -> Dict[str, Any]:
    """List all stored backup snapshots."""
    bdir = _expand_path(backup_dir)
    if not bdir.exists():
        return {"success": True, "backups": [], "count": 0, "directory": str(bdir)}

    backups = []
    for item in sorted(bdir.glob("*.tar.gz"), key=lambda x: x.stat().st_mtime, reverse=True):
        st = item.stat()
        backups.append({
            "filename": item.name,
            "full_path": str(item),
            "size_bytes": st.st_size,
            "size_human": _format_size(st.st_size),
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        })

    return {
        "success": True,
        "backups": backups,
        "count": len(backups),
        "directory": str(bdir)
    }


def verify_backup(backup_file: str) -> Dict[str, Any]:
    """Verify integrity of a tar.gz backup archive without extracting."""
    p = _expand_path(backup_file)
    if not p.exists():
        return {"success": False, "error": f"Backup file not found: {p}"}

    try:
        with tarfile.open(p, "r:gz") as tar:
            members = tar.getmembers()
            file_names = [m.name for m in members]
            total_uncompressed = sum(m.size for m in members)

        return {
            "success": True,
            "valid": True,
            "file_count": len(members),
            "uncompressed_size_human": _format_size(total_uncompressed),
            "files_sample": file_names[:20],
            "message": f"Archive is valid and contains {len(members)} files."
        }
    except Exception as e:
        return {"success": False, "valid": False, "error": f"Archive corrupted or invalid: {e}"}


def restore_backup(
    backup_file: str,
    destination_dir: str,
    create_safety_copy: bool = True
) -> Dict[str, Any]:
    """Restore archive contents into destination directory with optional pre-restore safety snapshot."""
    p = _expand_path(backup_file)
    dst = _expand_path(destination_dir)

    if not p.exists():
        return {"success": False, "error": f"Backup archive not found: {p}"}

    safety_res = None
    if create_safety_copy and dst.exists():
        safety_res = create_backup(str(dst), prefix="pre_restore_safety")

    dst.mkdir(parents=True, exist_ok=True)

    try:
        with tarfile.open(p, "r:gz") as tar:
            # Prevent zip/tar slip attacks
            resolved_dst = dst.resolve()
            for member in tar.getmembers():
                target_path = (dst / member.name).resolve()
                if not (target_path == resolved_dst or target_path.is_relative_to(resolved_dst)):
                    raise ValueError(f"Tar slip detected in archive: {member.name}")
            if hasattr(tarfile, "data_filter"):
                tar.extractall(dst, filter="data")
            else:
                tar.extractall(dst)

        return {
            "success": True,
            "backup_file": str(p),
            "destination": str(dst),
            "safety_snapshot": safety_res.get("backup_file") if safety_res else None,
            "message": f"Successfully restored {p.name} to {dst}"
        }
    except Exception as e:
        return {"success": False, "error": str(e), "destination": str(dst)}
