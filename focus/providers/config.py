"""Focus-only per-provider settings, stored apart from upstream params.

Key refs, retry policy, OpenRouter routing and Vertex coordinates are
bookkeeping the app owns; they must never reach an upstream request. They live
in their own ``config_json`` column so ``params_json`` stays what its name
says: upstream sampler defaults passed through to the provider.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from typing import Any


@dataclass
class ProviderConfig:
    api_keys: list[str] = field(default_factory=list)
    active_key: str | None = None
    retry: dict[str, Any] = field(default_factory=dict)
    or_route: str | None = None
    or_quant: str | None = None
    or_no_fallbacks: bool = True
    vertex_region: str = ""
    vertex_project_id: str = ""

    @classmethod
    def from_json(cls, raw: str | None) -> ProviderConfig:
        try:
            data = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return cls()
        if not isinstance(data, dict):
            return cls()
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})
