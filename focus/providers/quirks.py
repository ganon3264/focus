"""Provider request-quirk pipeline.

The ordered ``QUIRKS`` table is the single place that encodes cross-cutting,
provider- or model-specific request preprocessing. Each quirk is a predicate
plus a transform; adding one is a single entry, not an edit to the generation
flow. Wire-format assembly (``extra_body.reasoning``, ``thinking``, Google
config, etc.) deliberately stays in the adapter classes.

Ordering is load-bearing: modality filtering happens before caching, and the
native-reasoning remap runs after the stripping quirks and the prefill append
so the synthesized assistant turn is remapped too. Sampler keys consumed here
are stripped centrally via ``INTERNAL_SAMPLER_KEYS``.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ..core.request_transforms import (
    apply_claude_caching,
    drop_foreign_reasoning_details,
    filter_unsupported_modalities,
)
from ..core.tracked_fields import filter_reasoning_details, strip_thinking
from .google_safety import PASSTHROUGH_HARM_CATEGORIES, safety_settings_json
from .profile import INTERNAL_SAMPLER_KEYS, Capabilities, ProviderProfile
from .registry import profile_for
from .schema import provider_schema


def _is_openrouter(c: QuirkContext) -> bool:
    return c.prov.get("type") == "openrouter"


def _is_openrouter_google(c: QuirkContext) -> bool:
    return _is_openrouter(c) and c.model.startswith("google/")


def _preserve_thinking_mode(raw: Any) -> str:
    if isinstance(raw, str):
        v = raw.lower()
        if v in ("all", "true"):
            return "all"
        if v == "tool_only":
            return "tool_only"
        return "off"
    if raw is True:
        return "all"
    return "off"


@dataclass
class QuirkContext:
    provider: Any
    prov: dict
    model: str
    body: Any
    chat_id: str
    samplers: dict
    profile: ProviderProfile
    caps: Capabilities
    messages: list[dict]
    gen_kwargs: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Quirk:
    name: str
    applies: Callable[[QuirkContext], bool]
    run: Callable[[QuirkContext], Awaitable[None] | None]


def _filter_disabled_modalities(c: QuirkContext) -> None:
    if c.samplers.get("disable_multimodal", False):
        c.messages = filter_unsupported_modalities(c.messages, ["text"])


async def _filter_provider_modalities(c: QuirkContext) -> None:
    modalities = await c.provider.supported_modalities(c.model)
    if modalities:
        c.messages = filter_unsupported_modalities(c.messages, modalities)


async def _filter_unsupported_params(c: QuirkContext) -> None:
    """Drop forwarded sampler keys the upstream model doesn't advertise.

    OpenRouter publishes ``supported_parameters`` per model; without this a
    strict upstream (e.g. Xiaomi) rejects the whole request over an unsupported
    key like ``top_k``. Providers that expose no list are left untouched.
    """
    supported = await c.provider.supported_parameters(c.model)
    if not supported:
        return
    filterable = provider_schema()["types"].get(c.prov["type"], {}).get("capabilityFiltered", ())
    allowed = set(supported)
    for key in filterable:
        if key in c.samplers and key not in allowed:
            c.samplers.pop(key)


def _claude_cache(c: QuirkContext) -> None:
    if c.samplers.get("cache_enabled", False) and c.model.startswith("anthropic/claude"):
        c.messages = apply_claude_caching(
            c.messages,
            True,
            c.samplers.get("cache_ttl", "ephemeral"),
            c.samplers.get("cache_depth", 5),
        )


def _inject_google_safety(c: QuirkContext) -> None:
    """Relay Gemini safety settings to Google models accessed via OpenRouter.

    OpenRouter forwards top-level ``safety_settings`` to its Google upstreams
    verbatim. Always sent, matching the native Google adapters (which hardcode
    safety-off) — refusals are pure friction in a roleplay frontend.
    """
    c.gen_kwargs["safety_settings"] = safety_settings_json(PASSTHROUGH_HARM_CATEGORIES, "OFF")


def _strip_greeting(c: QuirkContext) -> None:
    for msg in c.messages:
        msg.pop("_greeting", None)


def _drop_foreign_reasoning(c: QuirkContext) -> None:
    drop_foreign_reasoning_details(c.messages, c.caps.normalizes_reasoning, c.model)


def _strip_thought_signatures(c: QuirkContext) -> None:
    for msg in c.messages:
        msg.pop("thought_signature", None)


def _apply_preserve_thinking(c: QuirkContext) -> None:
    mode = _preserve_thinking_mode(c.samplers.get("preserve_thinking", False))
    if mode == "off":
        for msg in c.messages:
            if msg.get("role") == "assistant":
                strip_thinking(msg, "off")
    elif mode == "tool_only":
        for msg in c.messages:
            if msg.get("role") == "assistant":
                strip_thinking(msg, "tool_only")


def _filter_reasoning_details(c: QuirkContext) -> None:
    for msg in c.messages:
        if msg.get("role") == "assistant":
            filter_reasoning_details(msg, c.caps.reasoning_formats)


def _remap_native_reasoning(c: QuirkContext) -> None:
    key = c.caps.reasoning_message_key
    if not key:
        return
    for msg in c.messages:
        if msg.get("role") == "assistant" and msg.get("reasoning"):
            msg[key] = msg.pop("reasoning")


def _append_prefill(c: QuirkContext) -> None:
    if (
        (c.body.continue_text is not None or c.body.continue_reasoning)
        and c.body.regenerate
        and c.provider.supports_prefill
    ):
        prefill_msg: dict = {"role": "assistant", "content": c.body.continue_text or ""}
        if c.body.continue_reasoning:
            prefill_msg["reasoning"] = c.body.continue_reasoning
        c.messages.append(prefill_msg)


def _context_kwargs(c: QuirkContext) -> None:
    for key in c.profile.context_kwargs:
        c.gen_kwargs[key] = c.chat_id


QUIRKS: tuple[Quirk, ...] = (
    Quirk("filter_disabled_modalities", lambda c: True, _filter_disabled_modalities),
    Quirk("filter_provider_modalities", lambda c: True, _filter_provider_modalities),
    Quirk(
        "filter_unsupported_params",
        lambda c: callable(getattr(c.provider, "supported_parameters", None)),
        _filter_unsupported_params,
    ),
    Quirk("claude_cache", lambda c: c.caps.supports_ephemeral_cache, _claude_cache),
    Quirk("google_safety_passthrough", _is_openrouter_google, _inject_google_safety),
    Quirk("strip_greeting", lambda c: True, _strip_greeting),
    Quirk("drop_foreign_reasoning", lambda c: True, _drop_foreign_reasoning),
    Quirk("strip_thought_signatures", lambda c: not c.caps.thought_signatures, _strip_thought_signatures),
    Quirk("preserve_thinking", lambda c: not c.caps.owns_reasoning, _apply_preserve_thinking),
    Quirk(
        "filter_reasoning_details",
        lambda c: c.caps.reasoning_formats is not None,
        _filter_reasoning_details,
    ),
    Quirk("append_prefill", lambda c: True, _append_prefill),
    Quirk("remap_native_reasoning", lambda c: bool(c.caps.reasoning_message_key), _remap_native_reasoning),
    Quirk("context_kwargs", lambda c: bool(c.profile.context_kwargs), _context_kwargs),
)


async def apply_request_quirks(
    prov: dict,
    body: Any,
    messages: list[dict],
    provider: Any,
    chat_id: str,
) -> tuple[list[dict], dict]:
    """Run the ordered quirk pipeline and return ``(messages, gen_kwargs)``."""
    profile = profile_for(prov["type"])
    ctx = QuirkContext(
        provider=provider,
        prov=prov,
        model=prov.get("model", ""),
        body=body,
        chat_id=chat_id,
        samplers=dict(body.samplers or {}),
        profile=profile,
        caps=profile.caps,
        messages=messages,
    )
    for quirk in QUIRKS:
        if quirk.applies(ctx):
            result = quirk.run(ctx)
            if inspect.isawaitable(result):
                await result
    for key in INTERNAL_SAMPLER_KEYS:
        ctx.samplers.pop(key, None)
    return ctx.messages, {**ctx.samplers, **ctx.gen_kwargs}
