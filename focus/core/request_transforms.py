"""Provider-agnostic message transforms.

Pure dict/list manipulation used by the request pipeline. Kept in ``core`` so
both ``focus.providers.quirks`` and ``focus.routers.stream_utils`` can import
them without a providers <-> routers cycle. They never touch network or DB.
"""

from __future__ import annotations


def filter_unsupported_modalities(messages: list[dict], supported_modalities: list[str] | None) -> list[dict]:
    """Strip media blocks (image_url, input_audio) for models that don't support them.

    If a model only accepts text, all image/audio/file parts are removed and
    single-text content arrays are collapsed back to plain strings.
    """
    if not supported_modalities:
        return messages

    can_image = "image" in supported_modalities
    can_audio = "audio" in supported_modalities
    can_file = "file" in supported_modalities

    if can_image and can_audio:
        return messages

    filtered: list[dict] = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            filtered.append(msg)
            continue

        new_parts = []
        for part in content:
            pt = part.get("type")
            if pt == "text":
                new_parts.append(part)
            elif pt == "image_url" and can_image:
                new_parts.append(part)
            elif pt == "input_audio" and can_audio:
                new_parts.append(part)
            elif pt == "file" and can_file:
                new_parts.append(part)

        if not new_parts:
            continue
        if len(new_parts) == 1 and new_parts[0].get("type") == "text":
            filtered.append({"role": msg["role"], "content": new_parts[0].get("text", "")})
        else:
            filtered.append({"role": msg["role"], "content": new_parts})

    return filtered


def apply_claude_caching(
    messages: list[dict],
    cache_enabled: bool,
    cache_ttl: str = "5m",
    cache_depth: int = 5,
) -> list[dict]:
    if not cache_enabled or not messages:
        return messages

    # cache_control is always {"type": "ephemeral"}; duration is the
    # separate "ttl" field ("5m" default/omitted, or "1h").
    cc: dict = {"type": "ephemeral", "ttl": "1h"} if cache_ttl == "1h" else {"type": "ephemeral"}

    # Strip existing cache control so we never exceed the 4-breakpoint limit
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    part.pop("cache_control", None)

    def _inject_cache(msg: dict) -> bool:
        content = msg.get("content")
        if isinstance(content, str):
            if not content:
                return False
            msg["content"] = [{"type": "text", "text": content, "cache_control": cc}]
            return True
        if isinstance(content, list) and content:
            # cache_control is valid on any block type (text, image,
            # tool_use, tool_result, document) - just tag the last one.
            for part in reversed(content):
                if isinstance(part, dict) and part.get("type"):
                    part["cache_control"] = cc
                    return True
        return False

    # 1. Always cache the system/character instructions at the very beginning
    _inject_cache(messages[0])

    # 2. Sliding breakpoint further back in the conversation
    user_indices = [i for i, msg in enumerate(messages) if msg.get("role") == "user"]

    bp_idx = None
    if len(user_indices) >= cache_depth + 1:
        bp_idx = user_indices[-(cache_depth + 1)]
    elif len(user_indices) > 1:
        bp_idx = user_indices[-2]

    # Skip if it's the same message as the system breakpoint (avoid wasted work)
    if bp_idx is not None and bp_idx != 0:
        _inject_cache(messages[bp_idx])

    for msg in messages:
        msg.pop("_greeting", None)

    return messages


def drop_foreign_reasoning_details(messages: list[dict], is_openrouter: bool, current_model: str) -> None:
    """Clear the internal source-model tag, dropping foreign reasoning_detail blocks.

    OpenRouter normalizes reasoning across backends, but the detail blocks it
    returns carry backend-specific schemas (Anthropic signatures, OpenAI
    encrypted blobs) that are only valid for the model that produced them.
    When a chat switches models mid-conversation, only the plaintext
    ``reasoning`` field may be replayed for foreign turns.
    """
    for msg in messages:
        src_model = msg.pop("_src_model", None)
        if is_openrouter and msg.get("role") == "assistant" and src_model and src_model != current_model:
            msg.pop("reasoning_details", None)
