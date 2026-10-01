from __future__ import annotations

import json

DEFAULT_SUMMARY_INSTRUCTION = (
    "OOC: Summarize the conversation so far. Preserve the key facts, the "
    "current relationship and emotional state, and any unresolved threads or "
    "commitments. Write it in the same language as the conversation. Output "
    "only the summary."
)

DEFAULT_SUMMARY_KEEP = 20
DEFAULT_SUMMARY_MAX_TOKENS = 8192
DEFAULT_SUMMARY_ROLE = "system"

# The pieces a forked chat injects as leading context. Presets opt in by
# referencing the macros in a block; without a reference the same default
# wrapper is injected before the chat history.
SUMMARY_MACROS = ("summary", "summary_pins", "summary_messages", "summary_media")

DEFAULT_SUMMARY_TEMPLATE = (
    "<summary>\n{{summary}}\n</summary>\n\n"
    "<pinned_messages>\n{{summary_pins}}\n</pinned_messages>\n\n"
    "<media_messages>\n{{summary_media}}\n</media_messages>\n\n"
    "<last_messages>\n{{summary_messages}}\n</last_messages>"
)


def _parse_settings(settings) -> dict:
    if isinstance(settings, dict):
        return settings
    try:
        return json.loads(settings or "{}")
    except (TypeError, ValueError):
        return {}


def summary_config(preset_blocks=None, settings=None) -> dict:
    """Resolve summary settings from a preset's blocks and ``settings_json``.

    ``active`` is False when the settings are disabled, or when a Summary block
    exists but is disabled. With no Summary block at all the built-in defaults
    apply, keeping every existing preset working.
    """
    blocks = [b for b in (preset_blocks or []) if b.get("block_type") == "summary"]
    block = next((b for b in blocks if b.get("enabled")), None)
    raw = _parse_settings(settings).get("summary") or {}

    try:
        keep = int(raw.get("keep"))
    except (TypeError, ValueError):
        keep = DEFAULT_SUMMARY_KEEP

    try:
        max_tokens = int(raw.get("max_tokens"))
    except (TypeError, ValueError):
        max_tokens = DEFAULT_SUMMARY_MAX_TOKENS

    return {
        "active": bool(raw.get("enabled", True)) and (not blocks or block is not None),
        "instruction": (raw.get("instruction") or "").strip()
        or DEFAULT_SUMMARY_INSTRUCTION,
        "keep": max(0, keep),
        # 0 = no explicit cap: the provider's params (or its adapter default) apply.
        "max_tokens": max(0, max_tokens),
        "provider_id": (raw.get("provider_id") or "").strip(),
    }
