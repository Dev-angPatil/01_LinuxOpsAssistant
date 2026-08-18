"""Model Manager package for offline edge AI models."""

from ops_assistant.model_manager.downloader import ModelDownloader, DEFAULT_MODELS, get_default_models_dir

__all__ = ["ModelDownloader", "DEFAULT_MODELS", "get_default_models_dir"]
