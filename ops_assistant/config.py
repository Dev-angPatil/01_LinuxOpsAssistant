"""Configuration and State Persistence Manager for Linux Operations Assistant."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def get_config_dir() -> Path:
    """Return the configuration directory path (~/.ops_assistant)."""
    home = Path.home()
    cfg_dir = home / ".ops_assistant"
    try:
        cfg_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Fallback to local project directory if home is not writable
        cfg_dir = Path(__file__).resolve().parent.parent / ".ops_config"
        cfg_dir.mkdir(parents=True, exist_ok=True)
    return cfg_dir


def get_config_file() -> Path:
    """Return the path to config.json."""
    return get_config_dir() / "config.json"


DEFAULT_CONFIG: Dict[str, Any] = {
    "setup_completed": False,
    "provider": "auto",  # auto, deterministic, gguf, ollama
    "active_model_key": None,
    "active_model_path": None,
    "hardware_tier": None,
    "recommended_threads": 4,
    "recommended_ctx_size": 2048,
    "recommended_gpu_layers": 0,
    "ollama_endpoint": "http://localhost:11434/api/generate",
    "ollama_model": "llama3:8b",
    "auto_check_updates": True,
}


class ConfigManager:
    """Handles reading, updating, and saving application configuration."""

    def __init__(self, config_file: Optional[Path] = None):
        self.config_file = config_file or get_config_file()

    def load(self) -> Dict[str, Any]:
        """Load configuration from disk, falling back to defaults."""
        if not self.config_file.exists():
            return dict(DEFAULT_CONFIG)
        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                saved = json.load(f)
            merged = dict(DEFAULT_CONFIG)
            merged.update(saved)
            return merged
        except Exception:
            return dict(DEFAULT_CONFIG)

    def save(self, config: Dict[str, Any]) -> bool:
        """Persist configuration dictionary to disk."""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            return True
        except Exception:
            return False

    def is_setup_completed(self) -> bool:
        """Check if the user has completed the initial setup wizard."""
        cfg = self.load()
        return bool(cfg.get("setup_completed", False))

    def set_setup_completed(
        self,
        provider: str = "auto",
        model_key: Optional[str] = None,
        model_path: Optional[str] = None,
        hardware_tier: Optional[str] = None,
        threads: Optional[int] = None,
        ctx_size: Optional[int] = None,
        gpu_layers: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Mark setup as completed with specified settings."""
        cfg = self.load()
        cfg["setup_completed"] = True
        cfg["provider"] = provider
        if model_key:
            cfg["active_model_key"] = model_key
        if model_path:
            cfg["active_model_path"] = str(model_path)
        if hardware_tier:
            cfg["hardware_tier"] = hardware_tier
        if threads is not None:
            cfg["recommended_threads"] = threads
        if ctx_size is not None:
            cfg["recommended_ctx_size"] = ctx_size
        if gpu_layers is not None:
            cfg["recommended_gpu_layers"] = gpu_layers

        self.save(cfg)
        return cfg

    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value."""
        return self.load().get(key, default)

    def set(self, key: str, value: Any) -> bool:
        """Set a single configuration key."""
        cfg = self.load()
        cfg[key] = value
        return self.save(cfg)


# Global singleton helper
_config_manager = ConfigManager()


def get_config() -> Dict[str, Any]:
    return _config_manager.load()


def save_config(config: Dict[str, Any]) -> bool:
    return _config_manager.save(config)


def is_setup_completed() -> bool:
    return _config_manager.is_setup_completed()


def set_setup_completed(**kwargs) -> Dict[str, Any]:
    return _config_manager.set_setup_completed(**kwargs)
