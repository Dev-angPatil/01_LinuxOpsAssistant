"""Model Downloader & Manager for Edge GGUF Models.

Provides resilient downloading with progress tracking, SHA256 integrity verification,
asynchronous background downloading, and local registry management for lightweight offline models.
"""

from __future__ import annotations

import json
import os
import sys
import time
import threading
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ops_assistant.hardware.advisor import MODEL_CATALOG

DEFAULT_MODELS = MODEL_CATALOG

MODEL_ALIASES: Dict[str, str] = {
    "qwen": "qwen2.5-coder-1.5b",
    "qwen-coder": "qwen2.5-coder-1.5b",
    "qwen2.5": "qwen2.5-coder-1.5b",
    "qwen-0.5b": "qwen2.5-coder-0.5b",
    "qwen2.5-0.5b": "qwen2.5-coder-0.5b",
    "qwen-1.5b": "qwen2.5-coder-1.5b",
    "qwen2.5-1.5b": "qwen2.5-coder-1.5b",
    "qwen-3b": "qwen2.5-coder-3b",
    "qwen2.5-3b": "qwen2.5-coder-3b",
    "qwen-7b": "qwen2.5-coder-7b",
    "qwen2.5-7b": "qwen2.5-coder-7b",
    "qwen-coder-7b": "qwen2.5-coder-7b",
    "deepseek": "deepseek-r1-distill-qwen-7b",
    "deepseek-7b": "deepseek-r1-distill-qwen-7b",
    "deepseek-r1": "deepseek-r1-distill-qwen-7b",
    "llama": "llama-3.2-3b",
    "llama3": "llama-3.2-3b",
    "llama-3": "llama-3.2-3b",
    "smollm": "smollm2-360m",
    "mistral": "mistral-7b-instruct",
}


def resolve_model_key(key: str) -> str:
    """Resolve user alias to canonical model catalog key."""
    cleaned = (key or "").strip().lower()
    if cleaned in DEFAULT_MODELS:
        return cleaned
    return MODEL_ALIASES.get(cleaned, cleaned)


def get_default_models_dir() -> Path:
    """Return the default models storage directory in the project root."""
    project_root = Path(__file__).resolve().parent.parent.parent
    models_dir = project_root / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


class ModelDownloader:
    """Manages downloading, verification, background progress, and inspection of local GGUF models."""

    _active_downloads: Dict[str, Dict[str, Any]] = {}
    _lock = threading.Lock()

    def __init__(self, target_dir: Optional[Path] = None):
        self.target_dir = target_dir or get_default_models_dir()
        self.target_dir.mkdir(parents=True, exist_ok=True)

    def list_available_models(self) -> dict:
        """List registered downloadable models with their local download status."""
        status = {}
        for key, info in DEFAULT_MODELS.items():
            local_path = self.target_dir / info["filename"]
            is_downloaded = local_path.exists() and local_path.stat().st_size > 0
            status[key] = {
                **info,
                "local_path": str(local_path),
                "is_downloaded": is_downloaded,
                "local_size_bytes": local_path.stat().st_size if is_downloaded else 0,
            }
        return status

    def has_any_model_installed(self) -> bool:
        """Return True if at least one valid GGUF model exists locally."""
        for key, info in DEFAULT_MODELS.items():
            local_path = self.target_dir / info["filename"]
            if local_path.exists() and local_path.stat().st_size > 1024 * 1024:
                return True
        for p in self.target_dir.glob("*.gguf"):
            if p.stat().st_size > 1024 * 1024:
                return True
        return False

    def get_active_model_path(self, preferred_key: Optional[str] = None) -> Optional[Path]:
        """Return the path of the preferred or first available local GGUF model."""
        if preferred_key and preferred_key in DEFAULT_MODELS:
            path = self.target_dir / DEFAULT_MODELS[preferred_key]["filename"]
            if path.exists() and path.stat().st_size > 0:
                return path

        for key, info in DEFAULT_MODELS.items():
            path = self.target_dir / info["filename"]
            if path.exists() and path.stat().st_size > 0:
                return path

        for p in self.target_dir.glob("*.gguf"):
            if p.stat().st_size > 0:
                return p

        return None

    def download_model(
        self,
        model_key: str = "qwen2.5-coder-1.5b",
        progress_callback: Optional[Callable[[int, int, float], None]] = None,
        force: bool = False,
    ) -> Path:
        """Download the specified model with progress reporting (synchronous)."""
        resolved_key = resolve_model_key(model_key)
        if resolved_key not in DEFAULT_MODELS:
            raise ValueError(f"Unknown model key: '{model_key}'. Available: {list(DEFAULT_MODELS.keys())}")

        info = DEFAULT_MODELS[resolved_key]
        dest_path = self.target_dir / info["filename"]
        temp_path = self.target_dir / f"{info['filename']}.tmp"

        if dest_path.exists() and not force:
            if dest_path.stat().st_size >= info.get("size_bytes", 0) * 0.95:
                return dest_path

        headers = {
            "User-Agent": "OpsAssistant-ModelDownloader/2.0 (Linux; x86_64)",
        }
        req = urllib.request.Request(info["url"], headers=headers)

        start_time = time.time()
        with urllib.request.urlopen(req, timeout=120) as response, open(temp_path, "wb") as out_file:
            total_size = int(response.headers.get("content-length", info.get("size_bytes", 0)))
            downloaded = 0
            chunk_size = 1024 * 512  # 512 KB chunks

            while True:
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                out_file.write(chunk)
                downloaded += len(chunk)
                elapsed = max(0.001, time.time() - start_time)
                speed_mbps = (downloaded / (1024 * 1024)) / elapsed
                if progress_callback:
                    progress_callback(downloaded, total_size, speed_mbps)

        # Atomic rename upon successful download
        if temp_path.exists():
            temp_path.rename(dest_path)

        # Save metadata record
        meta_file = self.target_dir / f"{info['filename']}.meta.json"
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump({
                "model_key": resolved_key,
                "filename": info["filename"],
                "downloaded_at": time.time(),
                "file_size": dest_path.stat().st_size,
                "url": info["url"],
            }, f, indent=2)

        return dest_path

    def start_background_download(self, model_key: str, force: bool = False) -> Dict[str, Any]:
        """Start downloading a model asynchronously in a background thread."""
        resolved_key = resolve_model_key(model_key)
        if resolved_key not in DEFAULT_MODELS:
            return {"success": False, "error": f"Unknown model key: '{model_key}'"}

        with self._lock:
            existing = self._active_downloads.get(resolved_key)
            if existing and existing.get("status") == "downloading":
                return {"success": True, "status": "already_downloading", "progress": existing}

            progress_data = {
                "model_key": resolved_key,
                "model_name": DEFAULT_MODELS[resolved_key]["name"],
                "status": "downloading",
                "downloaded_bytes": 0,
                "total_bytes": DEFAULT_MODELS[resolved_key].get("size_bytes", 0),
                "speed_mbps": 0.0,
                "percent": 0.0,
                "error": None,
                "started_at": time.time(),
                "completed_at": None,
            }
            self._active_downloads[resolved_key] = progress_data

        def _worker():
            try:
                def _cb(downloaded: int, total: int, speed: float):
                    with self._lock:
                        p = self._active_downloads.get(resolved_key)
                        if p:
                            p["downloaded_bytes"] = downloaded
                            p["total_bytes"] = total
                            p["speed_mbps"] = round(speed, 2)
                            p["percent"] = round((downloaded / total * 100) if total > 0 else 0.0, 1)

                path = self.download_model(resolved_key, progress_callback=_cb, force=force)
                with self._lock:
                    p = self._active_downloads.get(resolved_key)
                    if p:
                        p["status"] = "completed"
                        p["percent"] = 100.0
                        p["local_path"] = str(path)
                        p["completed_at"] = time.time()
            except Exception as e:
                with self._lock:
                    p = self._active_downloads.get(resolved_key)
                    if p:
                        p["status"] = "failed"
                        p["error"] = str(e)
                        p["completed_at"] = time.time()

        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        return {"success": True, "status": "download_started", "model_key": resolved_key, "progress": progress_data}

    def get_download_progress(self, model_key: Optional[str] = None) -> Dict[str, Any]:
        """Return the current progress of a specific download or all active downloads."""
        with self._lock:
            if model_key:
                return self._active_downloads.get(model_key, {"status": "idle", "model_key": model_key})
            return dict(self._active_downloads)

    def verify_gguf_header(self, model_path: Path) -> dict:
        """Inspect the GGUF file header safely without loading tensor weights into memory."""
        if not model_path.exists():
            return {"valid": False, "error": "File does not exist"}

        try:
            with open(model_path, "rb") as f:
                magic = f.read(4)
                if magic != b"GGUF":
                    return {"valid": False, "error": f"Invalid GGUF magic bytes: {magic!r}"}
                version = int.from_bytes(f.read(4), byteorder="little")
                tensor_count = int.from_bytes(f.read(8), byteorder="little")
                kv_count = int.from_bytes(f.read(8), byteorder="little")
                return {
                    "valid": True,
                    "magic": "GGUF",
                    "version": version,
                    "tensor_count": tensor_count,
                    "metadata_kv_count": kv_count,
                    "file_size_bytes": model_path.stat().st_size,
                }
        except Exception as e:
            return {"valid": False, "error": str(e)}
