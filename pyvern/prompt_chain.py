from __future__ import annotations
import base64
import re
from pathlib import Path
from typing import Any


def apply_macros(text: str, macros: dict[str, str]) -> str:
    for key, value in macros.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def _load_image(image_row: dict) -> dict:
    """Read an image from disk and return an OpenAI-format image_url block."""
    data = Path(image_row["image_path"]).read_bytes()
    b64 = base64.b64encode(data).decode()
    mime = image_row.get("mime_type", "image/png")
    return {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}


def _build_content(text: str, images: list[dict]) -> str | list:
    """
    Return plain string if no images, or a multimodal content array if images present.
    Images come after text within the same block.
    """
    if not images:
        return text
    parts: list[dict] = []
    if text:
        parts.append({"type": "text", "text": text})
    parts.extend(_load_image(img) for img in images)
    return parts


def _merge_consecutive(messages: list[dict]) -> list[dict]:
    """
    Merge adjacent messages that share the same role into one.
    Text parts are joined with \\n\\n.
    If either part has images the result is normalized to a content array.
    """
    if not messages:
        return []

    def to_parts(content) -> list[dict]:
        if isinstance(content, str):
            return [{"type": "text", "text": content}] if content else []
        return list(content)

    def merge_content(a, b):
        all_text = (
            isinstance(a, str) and isinstance(b, str)
        )
        if all_text:
            sep = "\n\n" if a and b else ""
            return a + sep + b
        # At least one side has images — normalize both to arrays
        return to_parts(a) + to_parts(b)

    result = [dict(messages[0])]
    for msg in messages[1:]:
        last = result[-1]
        if msg["role"] == last["role"]:
            result[-1] = {
                "role": last["role"],
                "content": merge_content(last["content"], msg["content"]),
            }
        else:
            result.append(dict(msg))
    return result


def assemble_prompt(
    preset_blocks: list[dict[str, Any]],
    chat_history: list[dict[str, str]],
    char_data: dict[str, str],
    char_own_blocks: list[dict[str, Any]],
    macros: dict[str, str],
    block_images: dict[str, list[dict]] | None = None,
) -> list[dict[str, str]]:
    """
    Returns the full messages list ready to send to the provider.

    preset_blocks:   rows from preset_blocks ordered by position.
    chat_history:    list of {"role": ..., "content": ...} from the DB.
    char_data:       normalised character card fields.
    char_own_blocks: rows from char_blocks for the active character, ordered by position.
    macros:          substitution dict built from char_data + persona.
    block_images:    mapping of block_id → list of image rows, for multimodal blocks.
    """
    if block_images is None:
        block_images = {}

    active = [b for b in preset_blocks if b["enabled"]]
    active.sort(key=lambda b: b["position"])

    pre_history:  list[dict] = []
    post_history: list[dict] = []
    history_seen = False

    for block in active:
        btype = block["block_type"]
        target = post_history if history_seen else pre_history

        if btype == "chat_history":
            history_seen = True
            continue

        images = block_images.get(block["id"], [])

        if btype == "text":
            text = apply_macros(block["content"], macros).strip()
            content = _build_content(text, images)
            if content:
                target.append({"role": block["role"], "content": content})

        elif btype == "char_description":
            text = apply_macros(char_data.get("description", ""), macros).strip()
            content = _build_content(text, images)
            if content:
                target.append({"role": block["role"], "content": content})

        elif btype == "char_personality":
            text = apply_macros(char_data.get("personality", ""), macros).strip()
            content = _build_content(text, images)
            if content:
                target.append({"role": block["role"], "content": content})

        elif btype == "user_persona":
            text = macros.get("persona", "").strip()
            content = _build_content(text, images)
            if content:
                target.append({"role": block["role"], "content": content})

        elif btype == "char_blocks":
            enabled = [b for b in char_own_blocks if b["enabled"]]
            enabled.sort(key=lambda b: b["position"])
            for cb in enabled:
                text = apply_macros(cb["content"], macros).strip()
                cb_images = block_images.get(cb["id"], [])
                content = _build_content(text, cb_images)
                if content:
                    target.append({"role": cb["role"], "content": content})

    # Strip <think>...</think> blocks from assistant messages
    cleaned_history = []
    for msg in chat_history:
        cleaned_msg = dict(msg)
        if cleaned_msg.get("role") == "assistant" and isinstance(cleaned_msg.get("content"), str):
            # Non-greedy match for <think> blocks across multiple lines
            cleaned_msg["content"] = re.sub(r'<think>.*?</think>', '', cleaned_msg["content"], flags=re.DOTALL).strip()
        cleaned_history.append(cleaned_msg)

    messages = (
        _merge_consecutive(pre_history)
        + cleaned_history
        + _merge_consecutive(post_history)
    )
    return messages
