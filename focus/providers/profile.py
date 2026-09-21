"""Declarative per-provider facts.

This module is pure data — no imports from the provider adapters — so it can be
imported by both the adapters and the request pipeline without cycles. Each
adapter declares a ``ProviderProfile`` as a class attribute; ``BaseProvider``
copies the capability flags onto the class so existing call sites
(``provider.supports_tools``) keep working.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Sampler keys consumed by the request pipeline and never forwarded upstream.
# Kept global because every provider type strips the same set today.
INTERNAL_SAMPLER_KEYS: frozenset[str] = frozenset({
    "disable_multimodal",
    "image_format",
    "cache_enabled",
    "cache_ttl",
    "cache_depth",
})


@dataclass(frozen=True)
class Capabilities:
    """Facts the orchestrator needs to know about a provider type."""

    supports_tools: bool = True
    supports_prefill: bool = True
    echoes_prefill: bool = True
    include_stream_options: bool = True
    # Gemini: thought signatures must be preserved and replayed.
    thought_signatures: bool = False
    # Providers that need ``reasoning`` remapped to a native key (deepseek/moonshot).
    native_reasoning_key: str | None = None
    # Reasoning-detail formats this provider accepts; None = pass everything.
    reasoning_formats: tuple[str, ...] | None = None
    # Claude-style ephemeral prompt caching.
    supports_ephemeral_cache: bool = False


@dataclass(frozen=True)
class ProviderProfile:
    caps: Capabilities = field(default_factory=Capabilities)
    # gen_kwargs set from the chat id, e.g. ("session_id",) for OpenRouter.
    context_kwargs: tuple[str, ...] = ()
