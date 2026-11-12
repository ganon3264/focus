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

# Model families that take Anthropic-style ``cache_control`` breakpoints. The
# transports that forward breakpoints (OpenRouter, NanoGPT) all accept these
# prefixes; whether a type forwards them at all is its profile's call.
CACHE_BREAKPOINT_MODELS: tuple[str, ...] = ("anthropic/claude", "google/gemini")

# Gemini's ephemeral cache has a fixed 5-minute TTL, so the 1-hour sampler is
# meaningless there and the request drops it.
FIXED_CACHE_TTL_MODELS: tuple[str, ...] = ("google/",)


@dataclass(frozen=True)
class Capabilities:
    """Facts the orchestrator needs to know about a provider type."""

    supports_tools: bool = True
    supports_prefill: bool = True
    echoes_prefill: bool = True
    include_stream_options: bool = True
    # Assistant ``reasoning`` is remapped to this message field before dispatch
    # (e.g. deepseek/moonshot's ``reasoning_content``). None = leave as-is.
    reasoning_message_key: str | None = None
    # Reasoning-detail formats this provider accepts; None = pass everything.
    reasoning_formats: tuple[str, ...] | None = None
    # Provider uses the ``thought_signature`` message field, so the pipeline
    # must not strip it. Independent of ``owns_reasoning``.
    thought_signatures: bool = False
    # Provider serializes its own reasoning history (e.g. Gemini thought
    # signatures); the generic ``preserve_thinking`` stripping must not run.
    owns_reasoning: bool = False
    # Transport normalizes reasoning across upstream backends and tracks the
    # source model, so foreign ``reasoning_details`` must be dropped.
    normalizes_reasoning: bool = False
    # Anthropic-style ephemeral prompt caching.
    supports_ephemeral_cache: bool = False
    # ...implemented as ``cache_control`` breakpoints in the message array, for
    # these model prefixes only. Empty = the transport forwards none; a provider
    # whose caching is a request-body flag leaves both fields alone and maps the
    # cache samplers itself.
    cache_breakpoint_models: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderProfile:
    caps: Capabilities = field(default_factory=Capabilities)
    # gen_kwargs set from the chat id, e.g. ("session_id",) for OpenRouter.
    context_kwargs: tuple[str, ...] = ()
