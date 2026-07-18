import json

from ..core.logger import get_logger
from ..core.utils import DEFAULT_OPENAI_COMPAT_BASE_URL
from .base import BaseProvider
from .deepseek import DeepseekProvider
from .google_aistudio import GoogleAIStudioProvider
from .google_vertex import GoogleVertexProvider
from .moonshot import MoonshotProvider
from .openai_compat import OpenAICompatProvider
from .openrouter import OpenRouterProvider

logger = get_logger("providers")

__all__ = [
    "BaseProvider",
    "OpenAICompatProvider",
    "OpenRouterProvider",
    "GoogleAIStudioProvider",
    "GoogleVertexProvider",
    "DeepseekProvider",
    "MoonshotProvider",
    "create_provider",
]


def create_provider(row: dict) -> BaseProvider:
    try:
        params = json.loads(row.get("params_json") or "{}")
    except json.JSONDecodeError:
        logger.error("Corrupted params_json for provider %s, using empty dict", row.get("id", "?"))
        params = {}
    ptype = row["type"]

    if ptype == "openai_compat":
        return OpenAICompatProvider(
            base_url=row["base_url"] or DEFAULT_OPENAI_COMPAT_BASE_URL,
            api_key=row["api_key"] or "",
            model=row["model"],
            params=params,
        )
    elif ptype == "openrouter":
        return OpenRouterProvider(
            api_key=row["api_key"] or "",
            model=row["model"],
            params=params,
        )
    elif ptype == "google_aistudio":
        return GoogleAIStudioProvider(
            api_key=row["api_key"] or "",
            model=row["model"],
            params=params,
        )
    elif ptype == "google_vertex":
        return GoogleVertexProvider(
            api_key=row["api_key"] or "",
            model=row["model"],
            params=params,
        )
    elif ptype == "deepseek":
        return DeepseekProvider(
            api_key=row["api_key"] or "",
            model=row["model"],
            params=params,
        )
    elif ptype == "moonshot":
        return MoonshotProvider(
            api_key=row["api_key"] or "",
            model=row["model"],
            params=params,
        )
    else:
        raise ValueError(f"Unknown provider type: {ptype!r}")
