"""
Prompt chain assembly.

A preset is an ordered list of blocks with one sentinel block (is_sentinel=1)
that marks where the actual chat history gets spliced in.

Blocks before the sentinel → prepended as messages
Sentinel position         → chat history is inserted here
Blocks after the sentinel → appended after history (rare but supported)

Macro substitution happens on all block content:
  {{char}}        → character name
  {{user}}        → user name (persona)
  {{description}} → character description
  {{personality}} → character personality
  {{scenario}}    → character scenario
  {{persona}}     → alias for {{personality}}
"""

from typing import Any


def apply_macros(text: str, macros: dict[str, str]) -> str:
    for key, value in macros.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def assemble_prompt(
    preset_blocks: list[dict[str, Any]],
    chat_history: list[dict[str, str]],
    macros: dict[str, str],
) -> list[dict[str, str]]:
    """
    Returns the full messages list ready to send to the provider.

    preset_blocks: all rows from preset_blocks for this preset, ordered by position.
                  Disabled blocks are skipped. The sentinel block is the splice point.
    chat_history:  list of {"role": ..., "content": ...} dicts from the DB.
    macros:        substitution dict.
    """

    sentinel_pos: float | None = None
    for b in preset_blocks:
        if b["is_sentinel"]:
            sentinel_pos = b["position"]
            break

    # Fallback: if no sentinel found, splice history at the very end
    if sentinel_pos is None:
        sentinel_pos = float("inf")

    active = [b for b in preset_blocks if b["enabled"] and not b["is_sentinel"]]
    active.sort(key=lambda b: b["position"])

    before = [b for b in active if b["position"] < sentinel_pos]
    after  = [b for b in active if b["position"] > sentinel_pos]

    messages: list[dict[str, str]] = []

    for block in before:
        content = apply_macros(block["content"], macros).strip()
        if content:
            messages.append({"role": block["role"], "content": content})

    messages.extend(chat_history)

    for block in after:
        content = apply_macros(block["content"], macros).strip()
        if content:
            messages.append({"role": block["role"], "content": content})

    return messages
