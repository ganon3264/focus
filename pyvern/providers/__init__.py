import json
from .base import BaseProvider
from .openai_compat import OpenAICompatProvider
from .openrouter import OpenRouterProvider
from .google_aistudio import GoogleAIStudioProvider
from .google_vertex import GoogleVertexProvider
from .deepseek import DeepseekProvider
from .moonshot import MoonshotProvider

from ..logger import get_logger

logger = get_logger("providers")

def create_provider(row: dict) -> BaseProvider:
    try:
        params = json.loads(row.get("params_json") or "{}")
    except json.JSONDecodeError:
        logger.error("Corrupted params_json for provider %s, using empty dict", row.get("id", "?"))
        params = {}
    ptype = row["type"]

    if ptype == "openai_compat":
        return OpenAICompatProvider(
            base_url=row["base_url"] or "http://localhost:8080/v1",
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
