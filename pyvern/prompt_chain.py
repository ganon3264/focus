from __future__ import annotations
import base64
import re
from pathlib import Path
from typing import Any


from pyvern.macros import apply_macros


def _load_media(media_row: dict) -> dict:
    """Read a media file from disk and return an OpenAI-format block."""
    path = media_row.get("image_path") or media_row.get("file_path")
    data = Path(path).read_bytes()
    b64 = base64.b64encode(data).decode()
    mime = media_row.get("mime_type", "image/png")
    
    if mime.startswith("audio/"):
        # Format might be extracted from mime type, e.g. audio/mpeg -> mp3
        fmt = mime.split("/")[-1].replace("mpeg", "mp3")
        return {
            "type": "input_audio",
            "input_audio": {
                "data": b64,
                "format": fmt
            }
        }
    
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
    parts.extend(_load_media(img) for img in images)
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

    # Separate in-chat injection blocks (injection_depth not null) from regular blocks
    in_chat_blocks = [b for b in active if b.get("injection_depth") is not None]
    active = [b for b in active if b.get("injection_depth") is None]

    # ── Two-pass variable resolution (order-independent, handles chains) ──
    variables = [b for b in active if b["block_type"] == "variable"]
    active = [b for b in active if b["block_type"] != "variable"]

    if variables:
        var_map: dict[str, str] = {}
        for v in variables:
            var_key = v["name"].split(":")[0] if ":" in v["name"] else v["name"]
            var_map[var_key] = v["content"]

        for _ in range(10):
            changed = False
            for key, content in var_map.items():
                resolved = apply_macros(content, macros).strip()
                if macros.get(key) != resolved:
                    macros[key] = resolved
                    changed = True
            if not changed:
                break

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
            char_images = block_images.get(char_data.get("id"), [])
            text = apply_macros(char_data.get("description", ""), macros).strip()
            content = _build_content(text, char_images)
            if content:
                target.append({"role": block["role"], "content": content})

        elif btype == "char_personality":
            char_images = block_images.get(char_data.get("id"), [])
            text = apply_macros(char_data.get("personality", ""), macros).strip()
            content = _build_content(text, char_images)
            if content:
                target.append({"role": block["role"], "content": content})

        elif btype == "user_persona":
            persona_id = macros.get("persona_id", "")
            persona_images = block_images.get(persona_id, []) if persona_id else []
            text = macros.get("persona", "").strip()
            content = _build_content(text, persona_images)
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

    # Extract <think>...</think> blocks from assistant messages
    cleaned_history = []
    for msg in chat_history:
        cleaned_msg = dict(msg)
        if cleaned_msg.get("role") == "assistant" and isinstance(cleaned_msg.get("content"), str):
            content = cleaned_msg["content"]
            
            # Find thought signature
            signature_match = re.search(r'<thought_signature>(.*?)</thought_signature>', content, flags=re.DOTALL)
            if signature_match:
                cleaned_msg["thought_signature"] = signature_match.group(1).strip()
                content = re.sub(r'<thought_signature>.*?</thought_signature>', '', content, flags=re.DOTALL).strip()
                
            # Find all think blocks
            thoughts = re.findall(r'<think>(.*?)</think>', content, flags=re.DOTALL)
            if thoughts:
                # Combine multiple blocks just in case, though usually there's only one
                cleaned_msg["reasoning"] = "\n\n".join(t.strip() for t in thoughts if t.strip())
            
            # Non-greedy match for <think> blocks across multiple lines to strip them
            cleaned_msg["content"] = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
            
        cleaned_history.append(cleaned_msg)

    # Inject in-chat blocks into cleaned_history at their specified depths
    if in_chat_blocks:
        from collections import defaultdict
        by_depth: dict[int, list] = defaultdict(list)
        for block in in_chat_blocks:
            if block["block_type"] == "text":
                by_depth[block["injection_depth"]].append(block)

        for depth in sorted(by_depth.keys(), reverse=True):
            blocks = sorted(by_depth[depth], key=lambda b: b.get("injection_order", 0))
            injected: list[dict] = []
            for block in blocks:
                text = apply_macros(block["content"], macros).strip()
                images = block_images.get(block["id"], [])
                content = _build_content(text, images)
                if content:
                    injected.append({"role": block["role"], "content": content})
            if not injected:
                continue
            injected = _merge_consecutive(injected)
            insert_at = max(0, len(cleaned_history) - depth)
            cleaned_history[insert_at:insert_at] = injected

    messages = _merge_consecutive(pre_history + cleaned_history + post_history)
    return messages
