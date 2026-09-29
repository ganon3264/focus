from __future__ import annotations

import json

DEFAULT_SUMMARY_INSTRUCTION = (
    "OOC: Summarize the conversation so far. Preserve the key facts, the "
    "current relationship and emotional state, and any unresolved threads or "
    "commitments. Write it in the same language as the conversation. Output "
    "only the summary."
)

DEFAULT_SUMMARY_KEEP = 20


def summary_config(preset_blocks: list[dict] | None) -> dict:
    """Resolve summary settings from a preset's ``summary`` block.

    ``active`` is False only when a Summary block exists but is disabled, so the
    user can turn summary context off. With no block at all the built-in
    defaults apply, keeping every existing preset working.
    """
    blocks = [b for b in (preset_blocks or []) if b.get("block_type") == "summary"]
    block = next((b for b in blocks if b.get("enabled")), None)

    config: dict = {}
    if block:
        try:
            config = json.loads(block.get("config_json") or "{}")
        except (TypeError, ValueError):
            config = {}

    try:
        keep = int(config.get("keep"))
    except (TypeError, ValueError):
        keep = DEFAULT_SUMMARY_KEEP

    return {
        "active": not blocks or block is not None,
        "block": block,
        "instruction": ((block or {}).get("content") or "").strip()
        or DEFAULT_SUMMARY_INSTRUCTION,
        "keep": max(0, keep),
        "provider_id": (config.get("provider_id") or "").strip(),
        "role": (block or {}).get("role") or "system",
    }
