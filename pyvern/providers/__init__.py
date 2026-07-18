import json
from .base import BaseProvider
from .openai_compat import OpenAICompatProvider
from .openrouter import OpenRouterProvider


def create_provider(row: dict) -> BaseProvider:
    params = json.loads(row.get("params_json") or "{}")
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
    else:
        raise ValueError(f"Unknown provider type: {ptype!r}")
