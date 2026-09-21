import json

from ..core.logger import get_logger
from .base import BaseProvider
from .deepseek import DeepseekProvider
from .google_aistudio import GoogleAIStudioProvider
from .google_vertex import GoogleVertexProvider
from .moonshot import MoonshotProvider
from .openai_compat import OpenAICompatProvider
from .openrouter import OpenRouterProvider
from .registry import get_provider_class, registered_types

logger = get_logger("providers")

# Importing the adapters self-registers them by ``type`` in registry.py.
__all__ = [
    "BaseProvider",
    "OpenAICompatProvider",
    "OpenRouterProvider",
    "GoogleAIStudioProvider",
    "GoogleVertexProvider",
    "DeepseekProvider",
    "MoonshotProvider",
    "create_provider",
    "registered_types",
]


def create_provider(row: dict) -> BaseProvider:
    try:
        params = json.loads(row.get("params_json") or "{}")
    except json.JSONDecodeError:
        logger.error("Corrupted params_json for provider %s, using empty dict", row.get("id", "?"))
        params = {}
    cls = get_provider_class(row["type"])
    return cls.from_row(row, params)
