"""
Desktop & OS Operations — freedesktop.org compliant GUI integration
for opening folders, launching files, viewing images, opening browsers,
and safe file moving/copying/trashing.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _expand_path(raw_path: str) -> Path:
    """Expand ~ and environment variables, resolve path."""
    return Path(os.path.expandvars(os.path.expanduser(raw_path))).resolve()


def open_folder(path: str = "~") -> Dict[str, Any]:
    """
    Open a directory in the default system file manager (e.g. Nautilus, Dolphin, Thunar).
    """
    p = _expand_path(path)
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            p = Path.home()
    elif not p.is_dir():
        p = p.parent

    # Try xdg-open first, fallback to known Linux file managers
    try:
        proc = subprocess.Popen(
            ["xdg-open", str(p)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return {
            "success": True,
            "path": str(p),
            "pid": proc.pid,
            "message": f"Opened directory in file manager: {p}",
            "action": "open_folder"
        }
    except FileNotFoundError:
        # Fallbacks
        for fm in ("nautilus", "dolphin", "thunar", "pcmanfm", "caja", "nemo"):
            if shutil.which(fm):
                proc = subprocess.Popen(
                    [fm, str(p)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                return {
                    "success": True,
                    "path": str(p),
                    "pid": proc.pid,
                    "file_manager": fm,
                    "message": f"Opened directory in {fm}: {p}",
                    "action": "open_folder"
                }
        return {
            "success": False,
            "path": str(p),
            "error": "No supported desktop file manager (xdg-open/nautilus/dolphin/thunar) found.",
            "action": "open_folder"
        }
    except Exception as e:
        return {
            "success": False,
            "path": str(p),
            "error": str(e),
            "action": "open_folder"
        }


def open_file(path: str) -> Dict[str, Any]:
    """
    Open a file using the system default application or editor.
    """
    p = _expand_path(path)
    if not p.exists():
        return {
            "success": False,
            "path": str(p),
            "error": f"File does not exist: {p}",
            "action": "open_file"
        }

    try:
        proc = subprocess.Popen(
            ["xdg-open", str(p)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        return {
            "success": True,
            "path": str(p),
            "pid": proc.pid,
            "message": f"Opened file in default application: {p}",
            "action": "open_file"
        }
    except FileNotFoundError:
        editor = os.environ.get("EDITOR", "nano")
        return {
            "success": False,
            "path": str(p),
            "error": f"xdg-open not available. You can view it with: {editor} {p}",
            "action": "open_file"
        }
    except Exception as e:
        return {
            "success": False,
            "path": str(p),
            "error": str(e),
            "action": "open_file"
        }


def open_image(path: str) -> Dict[str, Any]:
    """
    Open an image using the default desktop image viewer (eog, feh, xdg-open).
    """
    p = _expand_path(path)
    if not p.exists():
        return {
            "success": False,
            "path": str(p),
            "error": f"Image file does not exist: {p}",
            "action": "open_image"
        }

    try:
        viewers = ["xdg-open", "eog", "feh", "gwenview", "display", "shotwell"]
        for v in viewers:
            if shutil.which(v):
                proc = subprocess.Popen(
                    [v, str(p)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
                return {
                    "success": True,
                    "path": str(p),
                    "viewer": v,
                    "pid": proc.pid,
                    "message": f"Opened image with {v}: {p}",
                    "action": "open_image"
                }
        return {
            "success": False,
            "path": str(p),
            "error": "No image viewer or xdg-open found.",
            "action": "open_image"
        }
    except Exception as e:
        return {
            "success": False,
            "path": str(p),
            "error": str(e),
            "action": "open_image"
        }


def open_browser(url: str = "https://google.com") -> Dict[str, Any]:
    """
    Open a web URL in the user default web browser.
    """
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://", "file://", "about:")):
        clean_url = "https://" + clean_url

    try:
        opened = webbrowser.open(clean_url, new=2)
        if opened:
            return {
                "success": True,
                "url": clean_url,
                "message": f"Opened browser to: {clean_url}",
                "action": "open_browser"
            }
        else:
            proc = subprocess.Popen(
                ["xdg-open", clean_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
            return {
                "success": True,
                "url": clean_url,
                "pid": proc.pid,
                "message": f"Launched browser with xdg-open: {clean_url}",
                "action": "open_browser"
            }
    except Exception as e:
        return {
            "success": False,
            "url": clean_url,
            "error": str(e),
            "action": "open_browser"
        }


def move_path(src: str, dst: str) -> Dict[str, Any]:
    """
    Move a file or directory with existence checking and rollback tracking.
    """
    s = _expand_path(src)
    d = _expand_path(dst)

    if not s.exists():
        return {
            "success": False,
            "src": str(s),
            "dst": str(d),
            "error": f"Source path does not exist: {s}",
            "action": "move_path"
        }

    if d.is_dir():
        final_dst = d / s.name
    else:
        final_dst = d
        final_dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        shutil.move(str(s), str(final_dst))
        return {
            "success": True,
            "src": str(s),
            "dst": str(final_dst),
            "message": f"Moved {s} -> {final_dst}",
            "rollback_command": f"mv '{final_dst}' '{s}'",
            "action": "move_path"
        }
    except Exception as e:
        return {
            "success": False,
            "src": str(s),
            "dst": str(final_dst),
            "error": str(e),
            "action": "move_path"
        }


def copy_path(src: str, dst: str) -> Dict[str, Any]:
    """
    Copy a file or directory recursively.
    """
    s = _expand_path(src)
    d = _expand_path(dst)

    if not s.exists():
        return {
            "success": False,
            "src": str(s),
            "dst": str(d),
            "error": f"Source path does not exist: {s}",
            "action": "copy_path"
        }

    try:
        if s.is_dir():
            if d.exists() and d.is_dir():
                target = d / s.name
            else:
                target = d
            shutil.copytree(str(s), str(target), dirs_exist_ok=True)
        else:
            if d.is_dir():
                target = d / s.name
            else:
                target = d
                target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(s), str(target))

        return {
            "success": True,
            "src": str(s),
            "dst": str(target),
            "message": f"Copied {s} -> {target}",
            "rollback_command": f"rm -rf '{target}'",
            "action": "copy_path"
        }
    except Exception as e:
        return {
            "success": False,
            "src": str(s),
            "dst": str(d),
            "error": str(e),
            "action": "copy_path"
        }


def trash_path(path: str) -> Dict[str, Any]:
    """
    Safely move a file/directory to the user trash directory (~/.local/share/Trash/files)
    instead of permanently deleting it.
    """
    p = _expand_path(path)
    if not p.exists():
        return {
            "success": False,
            "path": str(p),
            "error": f"Path does not exist: {p}",
            "action": "trash_path"
        }

    trash_dir = Path.home() / ".local" / "share" / "Trash" / "files"
    trash_dir.mkdir(parents=True, exist_ok=True)

    dest = trash_dir / p.name
    counter = 1
    stem = p.stem
    suffix = p.suffix
    while dest.exists():
        dest = trash_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    try:
        shutil.move(str(p), str(dest))
        return {
            "success": True,
            "original_path": str(p),
            "trash_path": str(dest),
            "message": f"Safely trashed {p} -> {dest}",
            "rollback_command": f"mv '{dest}' '{p}'",
            "action": "trash_path"
        }
    except Exception as e:
        return {
            "success": False,
            "path": str(p),
            "error": str(e),
            "action": "trash_path"
        }
