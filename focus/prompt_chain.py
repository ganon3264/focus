from __future__ import annotations

import asyncio
import base64
import logging
import re
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image

from focus.core.macros import apply_macros
from focus.core.paths import COMPRESSED_DIR
from focus.core.utils import MACRO_MAX_PASSES, variable_group_name

logger = logging.getLogger("focus.prompt_chain")

MAX_IMAGE_B64 = 5 * 1024 * 1024  # 5 MB provider limit on base64 payload

MEDIA_PATTERN = re.compile(r"\{\{media:(\d+)\}\}")


async def _ensure_compressed(orig_path: str, mime: str) -> tuple[Path, str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _ensure_compressed_sync, orig_path, mime)


def _ensure_compressed_sync(orig_path: str, mime: str) -> tuple[Path, str]:
    """Return (compressed_file_path, output_mime) from a disk cache.

    Creates a compressed version on disk if missing or stale.
    Preserves PNG (with transparency) when possible; falls back to JPEG
    only when dimension reduction alone can't fit under MAX_IMAGE_B64.
    Cache invalidation is by mtime: compressed must be newer than original.
    """
    orig = Path(orig_path)
    stem = orig.stem
    png_cache = Path(COMPRESSED_DIR) / f"{stem}.png"
    jpg_cache = Path(COMPRESSED_DIR) / f"{stem}.jpg"

    try:
        orig_mtime = orig.stat().st_mtime
    except OSError:
        orig_mtime = 0

    if png_cache.exists() and png_cache.stat().st_mtime >= orig_mtime:
        return png_cache, "image/png"
    if jpg_cache.exists() and jpg_cache.stat().st_mtime >= orig_mtime:
        return jpg_cache, "image/jpeg"

    data = orig.read_bytes()

    if len(base64.b64encode(data).decode()) <= MAX_IMAGE_B64:
        if mime == "image/png":
            png_cache.write_bytes(data)
            return png_cache, "image/png"
        jpg_cache.write_bytes(data)
        return jpg_cache, "image/jpeg"

    img = Image.open(BytesIO(data))
    has_alpha = img.mode in ("RGBA", "LA", "P")

    if has_alpha:
        scale = 1.0
        while scale > 0.05:
            scale *= 0.8
            w = max(1, int(img.width * scale))
            h = max(1, int(img.height * scale))
            resized = img.resize((w, h), Image.LANCZOS)
            buf = BytesIO()
            resized.save(buf, format="PNG", optimize=True)
            if len(base64.b64encode(buf.getvalue()).decode()) <= MAX_IMAGE_B64:
                png_cache.write_bytes(buf.getvalue())
                return png_cache, "image/png"
        img = img.convert("RGB")

    for quality in (85, 65):
        scale = 1.0
        while scale > 0.05:
            scale *= 0.8
            w = max(1, int(img.width * scale))
            h = max(1, int(img.height * scale))
            resized = img.resize((w, h), Image.LANCZOS)
            if resized.mode in ("RGBA", "LA", "P"):
                resized = resized.convert("RGB")
            buf = BytesIO()
            resized.save(buf, format="JPEG", quality=quality)
            if len(base64.b64encode(buf.getvalue()).decode()) <= MAX_IMAGE_B64:
                jpg_cache.write_bytes(buf.getvalue())
                return jpg_cache, "image/jpeg"

    jpg_cache.write_bytes(buf.getvalue())
    return jpg_cache, "image/jpeg"


async def _load_media(media_row: dict) -> dict | None:
    """Read a media file from disk and return an OpenAI-format block."""
    path = media_row.get("image_path") or media_row.get("file_path")
    if not path:
        logger.warning("_load_media: no path in media_row %r", media_row.get("id"))
        return None
    if not Path(path).exists():
        logger.warning("_load_media: file not found %s", path)
        return None

    mime = media_row.get("mime_type", "image/png")

    if mime.startswith("audio/"):
        try:
            data = Path(path).read_bytes()
        except OSError as e:
            logger.warning("_load_media: cannot read %s: %s", path, e)
            return None
        fmt = mime.split("/")[-1].replace("mpeg", "mp3")
        return {
            "type": "input_audio",
            "input_audio": {"data": base64.b64encode(data).decode(), "format": fmt},
        }

    try:
        compressed_path, out_mime = await _ensure_compressed(path, mime)
        data = compressed_path.read_bytes()
    except OSError as e:
        logger.warning("_load_media: compression failed for %s: %s", path, e)
        return None

    return {
        "type": "image_url",
        "image_url": {"url": f"data:{out_mime};base64,{base64.b64encode(data).decode()}"},
    }


async def build_content(text: str, images: list[dict]) -> str | list:
    """
    Return plain string if no images, or a multimodal content array if images present.

    If the text contains {{media:x}} markers (1-based index), images are
    interleaved at the marker positions instead of being appended at the end.
    Out-of-range indices leave the raw marker in the text as a visible error.
    """
    if not images:
        return text

    matches = list(MEDIA_PATTERN.finditer(text))
    if not matches:
        parts: list[dict] = []
        if text:
            parts.append({"type": "text", "text": text})
        for img in images:
            m = await _load_media(img)
            if m is not None:
                parts.append(m)
        return parts

    parts: list[dict] = []
    last_end = 0

    for match in matches:
        raw_before = text[last_end : match.start()]
        text_before = raw_before.rstrip("\n") if images else raw_before
        if text_before:
            parts.append({"type": "text", "text": text_before})

        index = int(match.group(1))
        if 1 <= index <= len(images):
            img = images[index - 1]
            media_block = await _load_media(img)
            if media_block:
                parts.append(media_block)
        else:
            parts.append({"type": "text", "text": match.group(0)})

        last_end = match.end()

    raw_after = text[last_end:]
    text_after = raw_after.lstrip("\n") if images else raw_after
    if text_after:
        parts.append({"type": "text", "text": text_after})

    return parts


def _merge_consecutive(messages: list[dict]) -> list[dict]:
    """
    Merge adjacent messages that share the same role into one.
    Text parts are joined with \\n\\n.
    If either part has images the result is normalized to a content array.
    Extra metadata keys (non-role, non-content) are preserved from both sides.
    """
    if not messages:
        return []

    def to_parts(content) -> list[dict]:
        if isinstance(content, str):
            return [{"type": "text", "text": content}] if content else []
        return list(content)

    def merge_content(a, b):
        all_text = isinstance(a, str) and isinstance(b, str)
        if all_text:
            sep = "\n" if a and b else ""
            return a + sep + b
        return to_parts(a) + to_parts(b)

    result = [dict(messages[0])]
    for msg in messages[1:]:
        last = result[-1]
        if msg["role"] == last["role"]:
            # Never merge assistant messages that have tool_calls
            if msg.get("tool_calls") or last.get("tool_calls"):
                result.append(dict(msg))
                continue
            # Never merge tool-role messages (they have distinct tool_call_ids)
            if msg.get("role") == "tool" or last.get("role") == "tool":
                result.append(dict(msg))
                continue
            # Never merge internal (tool-injected) user messages with real ones
            if msg.get("internal") or last.get("internal"):
                result.append(dict(msg))
                continue
            merged_extra = {}
            for k, v in last.items():
                if k not in ("role", "content"):
                    merged_extra[k] = v
            for k, v in msg.items():
                if k not in ("role", "content"):
                    merged_extra[k] = v
            result[-1] = {
                "role": last["role"],
                "content": merge_content(last["content"], msg["content"]),
                **merged_extra,
            }
        else:
            result.append(dict(msg))
    return result


def partition_blocks(blocks: list[dict]) -> tuple[list[dict], list[dict], dict[str, list[dict]]]:
    """Split preset blocks into variable and non-variable buckets.

    Returns (var_blocks, regular_blocks, var_groups). var_groups maps each
    group name (everything before the first ':' in a block's name) to the
    list of variable blocks in that group.
    """
    var_blocks: list[dict] = []
    regular_blocks: list[dict] = []
    var_groups: dict[str, list[dict]] = {}
    for b in blocks:
        if b["block_type"] == "variable":
            var_blocks.append(b)
            var_groups.setdefault(variable_group_name(b["name"]), []).append(b)
        else:
            regular_blocks.append(b)
    return var_blocks, regular_blocks, var_groups


def resolve_variable_blocks(variable_blocks: list[dict], macros: dict[str, str]) -> None:
    """Resolve {{macro}} references inside variable blocks, mutating `macros`.

    Variables may reference each other (e.g. {{nickname}} -> {{user}}); iterates
    until the macros dict stabilises or MACRO_MAX_PASSES is reached.
    Resolved content is stripped of leading/trailing whitespace before being stored.
    """
    if not variable_blocks:
        return

    var_map: dict[str, str] = {}
    for v in variable_blocks:
        var_key = variable_group_name(v["name"])
        var_map[var_key] = v["content"]

    for _ in range(MACRO_MAX_PASSES):
        changed = False
        for key, content in var_map.items():
            resolved = apply_macros(content, macros).strip()
            if macros.get(key) != resolved:
                macros[key] = resolved
                changed = True
        if not changed:
            break


async def assemble_prompt(
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

    in_chat_blocks = [b for b in active if b.get("injection_depth") is not None]
    active = [b for b in active if b.get("injection_depth") is None]

    # Two-pass variable resolution (order-independent, handles chains)
    variables = [b for b in active if b["block_type"] == "variable"]
    active = [b for b in active if b["block_type"] != "variable"]
    resolve_variable_blocks(variables, macros)

    pre_history: list[dict] = []
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
            content = await build_content(text, images)
            if content or block.get("reasoning"):
                msg = {"role": block["role"], "content": content}
                if block["role"] == "assistant" and block.get("reasoning"):
                    msg["reasoning"] = apply_macros(block["reasoning"], macros)
                target.append(msg)

        elif btype == "char_description":
            char_images = block_images.get(char_data.get("id"), [])
            text = apply_macros(char_data.get("description", ""), macros).strip()
            content = await build_content(text, char_images)
            if content:
                target.append({"role": block["role"], "content": content})

        elif btype == "char_personality":
            char_images = block_images.get(char_data.get("id"), [])
            text = apply_macros(char_data.get("personality", ""), macros).strip()
            content = await build_content(text, char_images)
            if content:
                target.append({"role": block["role"], "content": content})

        elif btype == "user_persona":
            persona_id = macros.get("persona_id", "")
            persona_images = block_images.get(persona_id, []) if persona_id else []
            text = apply_macros(macros.get("persona", ""), macros).strip()
            content = await build_content(text, persona_images)
            if content:
                target.append({"role": block["role"], "content": content})

        elif btype == "char_blocks":
            enabled = [b for b in char_own_blocks if b["enabled"]]
            enabled.sort(key=lambda b: b["position"])
            for cb in enabled:
                text = apply_macros(cb["content"], macros).strip()
                cb_images = block_images.get(cb["id"], [])
                content = await build_content(text, cb_images)
                if content:
                    target.append({"role": cb["role"], "content": content})

    # Extract reasoning from assistant messages
    cleaned_history = []
    for msg in chat_history:
        cleaned_msg = dict(msg)
        if isinstance(cleaned_msg.get("content"), str):
            cleaned_msg["content"] = apply_macros(cleaned_msg["content"], macros)
        if cleaned_msg.get("role") == "assistant" and isinstance(cleaned_msg.get("content"), str):
            content = cleaned_msg["content"]

            if not cleaned_msg.get("reasoning"):
                signature_match = re.search(
                    r"<thought_signature>(.*?)</thought_signature>", content, flags=re.DOTALL
                )
                if signature_match:
                    cleaned_msg["thought_signature"] = signature_match.group(1).strip()
                    content = re.sub(
                        r"<thought_signature>.*?</thought_signature>", "", content, flags=re.DOTALL
                    ).strip()
                cleaned_msg["content"] = content

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
                content = await build_content(text, images)
                if content or (block["role"] == "assistant" and block.get("reasoning")):
                    msg = {"role": block["role"], "content": content}
                    if block["role"] == "assistant" and block.get("reasoning"):
                        msg["reasoning"] = apply_macros(block["reasoning"], macros)
                    injected.append(msg)
            if not injected:
                continue
            injected = _merge_consecutive(injected)
            insert_at = max(0, len(cleaned_history) - depth)
            cleaned_history[insert_at:insert_at] = injected

    messages = _merge_consecutive(pre_history + cleaned_history + post_history)
    return messages
