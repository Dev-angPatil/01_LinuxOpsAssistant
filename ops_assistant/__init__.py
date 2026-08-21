"""AI-Powered Linux Operations Assistant (ops-assistant)."""

__version__ = "2.0.0"
__author__ = "SSM Hackathon Team"

from ops_assistant.agent import (
    OpsAssistantAgent,
    QwenProvider,
    GeminiProvider,
    LlamaCppProvider,
    OllamaProvider,
)
from ops_assistant.models import (
    DiagnosticReport,
    SafetyLevel,
    SystemHealthSnapshot,
)

__all__ = [
    "OpsAssistantAgent",
    "QwenProvider",
    "GeminiProvider",
    "LlamaCppProvider",
    "OllamaProvider",
    "DiagnosticReport",
    "SafetyLevel",
    "SystemHealthSnapshot",
]

