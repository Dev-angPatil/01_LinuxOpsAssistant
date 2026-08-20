"""
Storage Operations — disk analysis, large-file discovery, log cleaning,
and directory organisation for the Linux Ops Assistant.

All mutating operations default to dry_run=True and return a structured
result dict that the CLI layer can present for confirmation before executing.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: List[str], timeout: int = 15) -> Tuple[int, str, str]:
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return p.returncode, p.stdout, p.stderr
    except FileNotFoundError:
        return 127, "", f"Command not found: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out after {timeout}s"


def _human_size(nbytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"


# ---------------------------------------------------------------------------
# File-type map for directory organisation
# ---------------------------------------------------------------------------

_TYPE_MAP: Dict[str, str] = {
    # Images
    ".jpg": "images", ".jpeg": "images", ".png": "images", ".gif": "images",
    ".bmp": "images", ".svg": "images", ".webp": "images", ".heic": "images",
    ".tiff": "images", ".ico": "images", ".raw": "images",
    # Videos
    ".mp4": "videos", ".mkv": "videos", ".avi": "videos", ".mov": "videos",
    ".wmv": "videos", ".flv": "videos", ".webm": "videos", ".m4v": "videos",
    # Audio
    ".mp3": "audio", ".flac": "audio", ".wav": "audio", ".aac": "audio",
    ".ogg": "audio", ".m4a": "audio", ".opus": "audio",
    # Documents
    ".pdf": "documents", ".doc": "documents", ".docx": "documents",
    ".odt": "documents", ".txt": "documents", ".md": "documents",
    ".rst": "documents", ".tex": "documents",
    # Spreadsheets / Presentations
    ".xls": "spreadsheets", ".xlsx": "spreadsheets", ".ods": "spreadsheets",
    ".csv": "spreadsheets",
    ".ppt": "presentations", ".pptx": "presentations", ".odp": "presentations",
    # Archives
    ".zip": "archives", ".tar": "archives", ".gz": "archives",
    ".bz2": "archives", ".xz": "archives", ".7z": "archives", ".rar": "archives",
    ".tgz": "archives", ".zst": "archives",
    # Code
    ".py": "code", ".js": "code", ".ts": "code", ".sh": "code",
    ".c": "code", ".cpp": "code", ".h": "code", ".rs": "code",
    ".go": "code", ".java": "code", ".rb": "code", ".php": "code",
    ".html": "code", ".css": "code", ".json": "code", ".xml": "code",
    ".yaml": "code", ".yml": "code", ".toml": "code",
    # Executables / packages
    ".deb": "packages", ".rpm": "packages", ".AppImage": "packages",
    ".flatpak": "packages", ".snap": "packages", ".exe": "packages",
    ".iso": "packages",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyse_disk(path: Optional[str] = None) -> Dict[str, Any]:
    """
    Return a structured disk usage summary from df + du on top-level dirs or given path.
    """
    result: Dict[str, Any] = {"partitions": [], "top_dirs": [], "errors": []}

    target = [path] if path and os.path.exists(path) else []
    # df -h output
    rc, stdout, stderr = _run(["df", "-h", "--output=source,fstype,size,used,avail,pcent,target"] + target)
    if rc == 0:
        lines = stdout.strip().splitlines()
        for line in lines[1:]:  # skip header
            parts = line.split()
            if len(parts) >= 7 and not parts[0].startswith("tmpfs") and not parts[0].startswith("devtmpfs"):
                try:
                    pct = int(parts[5].rstrip("%"))
                    result["partitions"].append({
                        "device": parts[0],
                        "fstype": parts[1],
                        "size": parts[2],
                        "used": parts[3],
                        "avail": parts[4],
                        "use_pct": pct,
                        "mountpoint": parts[6],
                        "status": "WARNING" if pct >= 85 else "OK",
                    })
                except (ValueError, IndexError):
                    pass
    else:
        result["errors"].append(f"df error: {stderr}")

    # du -sh on common large dirs or target path
    candidate_dirs = [path] if path and os.path.isdir(path) else ["/home", "/var", "/opt", "/tmp", "/usr"]
    for d in candidate_dirs:
        if os.path.isdir(d):
            rc2, out2, _ = _run(["du", "-sh", d], timeout=10)
            if rc2 == 0 and out2.strip():
                parts2 = out2.strip().split()
                if parts2:
                    result["top_dirs"].append({"path": d, "size": parts2[0]})

    return result


def find_large_files(
    search_path: str = "/",
    threshold_mb: int = 100,
    top_n: int = 20,
) -> Dict[str, Any]:
    """
    Find the largest files under *search_path* above *threshold_mb* MB.
    Returns sorted list of (path, size_bytes).
    """
    result: Dict[str, Any] = {"files": [], "search_path": search_path,
                               "threshold_mb": threshold_mb, "error": None}
    # Use find + sort; safer than du -a on huge trees
    cmd = [
        "find", search_path,
        "-xdev",           # don't cross device boundaries
        "-type", "f",
        "-size", f"+{threshold_mb}M",
        "-printf", "%s\t%p\n",
    ]
    rc, stdout, stderr = _run(cmd, timeout=30)
    if rc not in (0, 1):  # find may return 1 for permission errors on some dirs
        result["error"] = stderr
        return result

    entries: List[Tuple[int, str]] = []
    for line in stdout.strip().splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2:
            try:
                entries.append((int(parts[0]), parts[1]))
            except ValueError:
                pass

    entries.sort(key=lambda x: x[0], reverse=True)
    result["files"] = [
        {"path": p, "size_bytes": s, "size_human": _human_size(s)}
        for s, p in entries[:top_n]
    ]
    return result


def clean_logs(dry_run: bool = True) -> Dict[str, Any]:
    """
    Identify and optionally remove stale log files and old /tmp entries.

    Returns a plan dict with:
        - candidates: list of files/dirs that would be affected
        - freed_estimate: human-readable size estimate
        - executed: False if dry_run=True
        - actions: list of action results (only when dry_run=False)
    """
    candidates: List[Dict[str, Any]] = []
    total_bytes = 0

    # --- /var/log: rotated & compressed logs older than 7 days ---
    log_dir = Path("/var/log")
    if log_dir.exists():
        for f in log_dir.rglob("*"):
            if f.is_file() and (
                f.suffix in (".gz", ".bz2", ".xz", ".zst") or
                re.search(r"\.\d+$", f.name)  # e.g. syslog.1
            ):
                try:
                    stat = f.stat()
                    age_days = (
                        __import__("time").time() - stat.st_mtime
                    ) / 86400
                    if age_days > 7:
                        candidates.append({
                            "path": str(f),
                            "size_bytes": stat.st_size,
                            "size_human": _human_size(stat.st_size),
                            "age_days": round(age_days, 1),
                            "action": "delete",
                        })
                        total_bytes += stat.st_size
                except OSError:
                    pass

    # --- /tmp: files older than 3 days ---
    tmp_dir = Path("/tmp")
    if tmp_dir.exists():
        for f in tmp_dir.iterdir():
            if f.is_file():
                try:
                    stat = f.stat()
                    age_days = (
                        __import__("time").time() - stat.st_mtime
                    ) / 86400
                    if age_days > 3:
                        candidates.append({
                            "path": str(f),
                            "size_bytes": stat.st_size,
                            "size_human": _human_size(stat.st_size),
                            "age_days": round(age_days, 1),
                            "action": "delete",
                        })
                        total_bytes += stat.st_size
                except OSError:
                    pass

    plan: Dict[str, Any] = {
        "candidates": candidates,
        "freed_estimate": _human_size(total_bytes),
        "count": len(candidates),
        "dry_run": dry_run,
        "executed": False,
        "actions": [],
    }

    if not dry_run:
        for item in candidates:
            path = Path(item["path"])
            try:
                path.unlink()
                plan["actions"].append({"path": item["path"], "status": "deleted"})
            except OSError as e:
                plan["actions"].append({"path": item["path"], "status": "error", "error": str(e)})
        plan["executed"] = True

    return plan


def organise_directory(
    target_path: str,
    dry_run: bool = True,
) -> Dict[str, Any]:
    """
    Organise files in *target_path* into type-based subdirectories.

    The plan groups files by extension category (images/, videos/, documents/,
    archives/, code/, etc.) and optionally executes the moves.

    Returns a plan dict with list of moves and size summary.
    """
    base = Path(os.path.expanduser(target_path))
    if not base.is_dir():
        return {"error": f"Not a directory: {target_path}", "moves": []}

    moves: List[Dict[str, str]] = []
    skipped: List[str] = []

    for f in base.iterdir():
        if not f.is_file():
            continue
        if f.name.startswith("."):
            skipped.append(str(f))
            continue
        ext = f.suffix.lower()
        category = _TYPE_MAP.get(ext, "other")
        dest_dir = base / category
        dest_file = dest_dir / f.name
        # Handle name collisions
        if dest_file.exists():
            stem = f.stem
            suffix = f.suffix
            i = 1
            while dest_file.exists():
                dest_file = dest_dir / f"{stem}_{i}{suffix}"
                i += 1
        moves.append({
            "source": str(f),
            "destination": str(dest_file),
            "category": category,
            "filename": f.name,
        })

    plan: Dict[str, Any] = {
        "target_path": str(base),
        "directory": str(base),
        "moves": moves,
        "skipped": skipped,
        "categories": sorted({m["category"] for m in moves}),
        "total_files": len(moves),
        "moved_count": 0,
        "dry_run": dry_run,
        "executed": False,
        "errors": [],
        "rollback_command": None,
    }

    if not dry_run:
        moved_ok = 0
        for move in moves:
            src = Path(move["source"])
            dst = Path(move["destination"])
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
                move["status"] = "moved"
                moved_ok += 1
            except OSError as e:
                move["status"] = "error"
                move["error"] = str(e)
                plan["errors"].append(str(e))
        plan["executed"] = True
        plan["moved_count"] = moved_ok
        if moves:
            plan["rollback_command"] = f"# Revert moves under {base}"
    else:
        plan["moved_count"] = len(moves)

    return plan


def clean_logs_and_temp(dry_run: bool = True) -> Dict[str, Any]:
    """
    Clean rotated log files and temporary space.
    Wraps clean_logs with normalized summary keys.
    """
    plan = clean_logs(dry_run=dry_run)
    cleaned_count = sum(1 for a in plan.get("actions", []) if a.get("status") == "deleted") if not dry_run else plan.get("count", 0)
    return {
        **plan,
        "cleaned_count": cleaned_count,
        "freed_human": plan.get("freed_estimate", "0 B"),
        "success": True,
        "message": f"Successfully cleaned {cleaned_count} items, freed {plan.get('freed_estimate', '0 B')}" if not dry_run else f"Found {plan.get('count', 0)} cleanable items (~{plan.get('freed_estimate', '0 B')} reclaimable)"
    }

