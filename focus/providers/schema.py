"""Provider UI/forwarding schema, derived from the provider profiles.

This is the single backend source for the per-type facts the sampler UI needs:
defaults, reasoning-effort options, which fields are forwarded upstream, and
capabilities. It is embedded as ``window.PROVIDER_SCHEMA`` and consumed by
``static/js/core/provider-schema.js``.

The forward lists reproduce the legacy ``sampler-defaults.js`` ``build()``
functions exactly. Two value guards (``seed >= 0``, non-empty ``verbosity``)
are applied by the JS builder and noted there.
"""

from __future__ import annotations

from dataclasses import asdict
from functools import lru_cache
from typing import Any

from .profile import INTERNAL_SAMPLER_KEYS
from .registry import profile_for, registered_types

BASE_SAMPLER_DEFAULTS: dict[str, Any] = {
    "temperature": 1.0,
    "max_tokens": 8192,
    "top_p": 0.95,
    "top_k": 0,
    "min_p": 0,
    "frequency_penalty": 0.0,
    "presence_penalty": 0.0,
    "repetition_penalty": 1.0,
    "include_reasoning": True,
    "send_reasoning_history": True,
    "reasoning_effort": "max",
    "thinking_budget": 0,
    "stream_enabled": True,
    "enable_multimodal": True,
    "image_format": "webp",
    "cache_enabled": False,
    "cache_ttl": "ephemeral",
    "cache_depth": 5,
    "seed": -1,
    "verbosity": "",
}

# Fields forwarded for the active provider type regardless of reasoning.
_FORWARD_ALWAYS: dict[str, tuple[str, ...]] = {
    "openai_compat": ("frequency_penalty", "presence_penalty", "include_reasoning"),
    "deepseek": ("include_reasoning",),
    "moonshot": ("frequency_penalty", "presence_penalty", "include_reasoning"),
    "xiaomi_mimo": ("frequency_penalty", "presence_penalty", "include_reasoning"),
    "openrouter": (
        "top_k", "min_p", "repetition_penalty", "include_reasoning",
        "preserve_thinking", "seed", "verbosity",
        "cache_enabled", "cache_ttl", "cache_depth",
    ),
    "google_vertex": ("top_k", "send_reasoning_history", "include_reasoning"),
    "google_aistudio": ("top_k", "send_reasoning_history", "include_reasoning"),
}

# Fields forwarded only while ``include_reasoning`` is on.
_FORWARD_REASONING: dict[str, tuple[str, ...]] = {
    "openai_compat": ("reasoning_effort", "preserve_thinking"),
    "deepseek": ("preserve_thinking",),
    "moonshot": ("preserve_thinking", "reasoning_effort"),
    "xiaomi_mimo": ("preserve_thinking",),
    "openrouter": ("reasoning_effort", "thinking_budget"),
    "google_vertex": ("reasoning_effort",),
    "google_aistudio": ("reasoning_effort",),
}

# Forwarded keys consumed by the pipeline or remapped by the adapter (onto the
# wire ``reasoning`` field, Google thinking config, ...), so they aren't subject
# to per-model capability filtering.
_PIPELINE_CONTROL_KEYS: frozenset[str] = frozenset({
    "include_reasoning", "preserve_thinking", "reasoning_effort",
    "thinking_budget", "send_reasoning_history",
})


def capability_filtered_keys(ptype: str) -> set[str]:
    """Forwarded sampler keys whose support is decided by the model, not type."""
    keys = set(_FORWARD_ALWAYS.get(ptype, ())) | set(_FORWARD_REASONING.get(ptype, ()))
    return keys - INTERNAL_SAMPLER_KEYS - _PIPELINE_CONTROL_KEYS

_DEFAULT_OVERRIDES: dict[str, dict[str, Any]] = {
    "openai_compat": {"preserve_thinking": "tool_only", "image_format": "png"},
    "deepseek": {"preserve_thinking": "tool_only"},
    "moonshot": {"preserve_thinking": "tool_only"},
    "xiaomi_mimo": {"preserve_thinking": "tool_only", "image_format": "png"},
    "openrouter": {"top_k": 0, "min_p": 0, "repetition_penalty": 1.0, "preserve_thinking": "tool_only"},
    "google_vertex": {"include_reasoning": True, "reasoning_effort": ""},
    "google_aistudio": {"include_reasoning": True, "reasoning_effort": ""},
}

_EFFORT_OPTIONS: dict[str, tuple[tuple[str, str], ...]] = {
    "openrouter": (
        ("minimal", "Minimal"), ("low", "Low"), ("medium", "Medium"),
        ("high", "High"), ("xhigh", "X-High"), ("max", "Max"),
    ),
    "openai_compat": (("low", "Low"), ("medium", "Medium"), ("high", "High")),
    "deepseek": (("high", "High"), ("max", "Max")),
    "moonshot": (("low", "Low"), ("high", "High"), ("max", "Max")),
    "google_vertex": (
        ("MINIMAL", "Min"), ("LOW", "Low"), ("MEDIUM", "Med"), ("HIGH", "High"),
    ),
    "google_aistudio": (
        ("MINIMAL", "Min"), ("LOW", "Low"), ("MEDIUM", "Med"), ("HIGH", "High"),
    ),
}

_TYPE_LABELS: dict[str, str] = {
    "openai_compat": "OpenAI Compatible",
    "openrouter": "OpenRouter",
    "google_aistudio": "Google AI Studio",
    "google_vertex": "Google Vertex AI",
    "deepseek": "Deepseek",
    "moonshot": "Moonshot",
    "xiaomi_mimo": "Xiaomi MiMo",
}

# Provider create/edit form field visibility. Types absent here fall back to
# the default (base URL shown, no OR/Vertex fields).
_FORM_DEFAULT: dict[str, bool] = {
    "orFields": False, "modelInput": True, "baseUrl": True,
    "vertexFields": False, "modelRequired": True,
}
_FORM: dict[str, dict[str, bool]] = {
    "openrouter": {"orFields": True, "modelInput": True, "baseUrl": False, "vertexFields": False, "modelRequired": True},
    "google_vertex": {"orFields": False, "modelInput": True, "baseUrl": False, "vertexFields": True, "modelRequired": True},
    "google_aistudio": {"orFields": False, "modelInput": True, "baseUrl": False, "vertexFields": False, "modelRequired": True},
    "deepseek": {"orFields": False, "modelInput": True, "baseUrl": False, "vertexFields": False, "modelRequired": True},
    "moonshot": {"orFields": False, "modelInput": True, "baseUrl": False, "vertexFields": False, "modelRequired": True},
    "xiaomi_mimo": {"orFields": False, "modelInput": True, "baseUrl": True, "vertexFields": False, "modelRequired": True},
}

# Stable display order for provider-type pickers; unknown types sort last.
_DISPLAY_ORDER: tuple[str, ...] = (
    "openai_compat", "openrouter", "google_aistudio", "google_vertex", "deepseek", "moonshot", "xiaomi_mimo",
)


def _ordered_types() -> list[str]:
    known = set(registered_types())
    ordered = [t for t in _DISPLAY_ORDER if t in known]
    ordered += sorted(known - set(ordered))
    return ordered


def provider_type_options() -> list[dict]:
    """Ordered ``[{value, label}]`` for provider-type ``<select>`` elements."""
    return [{"value": t, "label": _TYPE_LABELS.get(t, t)} for t in _ordered_types()]



@lru_cache(maxsize=1)
def provider_schema() -> dict:
    types: dict[str, dict] = {}
    for ptype in _ordered_types():
        forward_always = list(_FORWARD_ALWAYS.get(ptype, ()))
        forward_reasoning = list(_FORWARD_REASONING.get(ptype, ()))
        types[ptype] = {
            "label": _TYPE_LABELS.get(ptype, ptype),
            "capabilities": asdict(profile_for(ptype).caps),
            "defaults": dict(_DEFAULT_OVERRIDES.get(ptype, {})),
            "forwardAlways": forward_always,
            "forwardReasoning": forward_reasoning,
            # Fields the sampler modal may show for this type. Visibility is the
            # union of forwarded fields; getters add reasoning/model gates.
            "visible": sorted(set(forward_always) | set(forward_reasoning)),
            # Forwarded keys the model may or may not accept (per OR capabilities).
            "capabilityFiltered": sorted(capability_filtered_keys(ptype)),
            "effortOptions": [
                {"value": v, "label": label}
                for v, label in _EFFORT_OPTIONS.get(ptype, _EFFORT_OPTIONS["openai_compat"])
            ],
            "form": dict(_FORM.get(ptype, _FORM_DEFAULT)),
        }
    return {"baseDefaults": dict(BASE_SAMPLER_DEFAULTS), "types": types}
