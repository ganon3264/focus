from __future__ import annotations

import asyncio
import html
import re
from functools import lru_cache

from focus.core.message_render import escape_html

# Bound worst-case work: a pathological pattern must not hang a generation or
# a page render. Python's re has no cancellation, so each text goes through a
# worker thread with a wall-clock cap; on timeout the original text is kept.
REGEX_TIMEOUT = 3.0
MAX_INPUT_LENGTH = 500_000

_FLAG_MAP = {"i": re.IGNORECASE, "m": re.MULTILINE, "s": re.DOTALL}


@lru_cache(maxsize=512)
def compile_pattern(pattern: str, flags: str):
    flag_value = 0
    for ch in flags or "":
        flag_value |= _FLAG_MAP.get(ch, 0)
    try:
        return re.compile(pattern, flag_value)
    except re.error:
        return None


def validate_pattern(pattern: str, flags: str = "") -> str | None:
    """Return an error message if *pattern* does not compile, else None."""
    if not pattern:
        return "pattern is empty"
    try:
        re.compile(pattern, sum(_FLAG_MAP.get(c, 0) for c in (flags or "")))
    except re.error as e:
        return str(e)
    return None


def _compiled(scripts: list[dict]) -> list[dict]:
    out = []
    for script in scripts:
        # Draft rows (no pattern yet) must never run: an empty regex matches
        # everywhere and would splice the replacement into every position.
        # Whitespace-only patterns are legitimate (they match whitespace), so
        # only a truly empty pattern is treated as a draft.
        if not (script.get("pattern") or ""):
            continue
        pattern = compile_pattern(script.get("pattern") or "", script.get("flags") or "")
        if pattern is not None:
            out.append({
                "pattern": pattern,
                "replacement": script.get("replacement") or "",
                "as_block": bool(script.get("as_block")),
                "name": (script.get("name") or "Block").strip() or "Block",
            })
    return out


def _apply_sync(text: str, compiled: list[dict]) -> str:
    for item in compiled:
        text = item["pattern"].sub(item["replacement"], text)
    return text


async def apply_text(text: str | None, scripts: list[dict]) -> str | None:
    if not text or not scripts:
        return text
    compiled = _compiled(scripts)
    if not compiled:
        return text
    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH]
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(_apply_sync, text, compiled), timeout=REGEX_TIMEOUT
        )
    except Exception:
        return text


async def apply_content(content, scripts: list[dict]):
    """Apply scripts to a wire-content value (str or multimodal part list)."""
    if not scripts:
        return content
    if isinstance(content, str):
        return await apply_text(content, scripts)
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                part = {**part, "text": await apply_text(part.get("text"), scripts)}
            parts.append(part)
        return parts
    return content


def placements(script: dict) -> set[str]:
    return {p for p in (script.get("placement") or "").split(",") if p}


def for_placement(scripts: list[dict], placement: str) -> list[dict]:
    return [s for s in scripts if placement in placements(s)]


def in_window(script: dict, depth: int) -> bool:
    if depth < int(script.get("min_depth") or 0):
        return False
    max_depth = int(script.get("max_depth") if script.get("max_depth") is not None else -1)
    return max_depth < 0 or depth <= max_depth


def _real_depths(entries: list) -> dict[int, int]:
    """Map list-index -> depth from the newest real (non-tool, non-internal)
    message. Synthetic tool messages and tool-result images are ignored."""
    indices = [
        i for i, e in enumerate(entries)
        if e.get("role") in ("user", "assistant") and not e.get("internal")
    ]
    total = len(indices)
    return {idx: total - 1 - rank for rank, idx in enumerate(indices)}


async def apply_to_prompt_history(history: list[dict], scripts: list[dict]) -> None:
    """Transform macro-resolved history in place (prompt-side scripts only)."""
    scripts = [s for s in scripts if s.get("apply_prompt")]
    if not scripts:
        return
    for index, depth in _real_depths(history).items():
        entry = history[index]
        windowed = [s for s in scripts if in_window(s, depth)]
        if not windowed:
            continue
        placement = "user" if entry.get("role") == "user" else "ai"
        content_scripts = for_placement(windowed, placement)
        if content_scripts:
            entry["content"] = await apply_content(entry.get("content"), content_scripts)
        if entry.get("role") == "assistant" and entry.get("reasoning"):
            reasoning_scripts = for_placement(windowed, "reasoning")
            if reasoning_scripts:
                entry["reasoning"] = await apply_text(entry["reasoning"], reasoning_scripts)


def _split_sync(text: str, compiled: list[dict]) -> list[dict]:
    """Apply scripts to one text value as an ordered pipeline.

    Returns a mixed list of parts:
      {"kind": "text",  "text": str}
      {"kind": "block", "text": str, "title": str}

    Plain scripts substitute in place; block scripts split the current text
    parts on every match and emit the capture group as a block. Later scripts
    (of either kind) keep operating on the pieces, so ordering still matters.
    """
    parts: list[dict] = [{"kind": "text", "text": text}]
    for item in compiled:
        pattern = item["pattern"]
        if not item["as_block"]:
            parts = [
                {
                    "kind": part["kind"],
                    "text": pattern.sub(item["replacement"], part["text"]),
                    **({"title": part["title"]} if "title" in part else {}),
                }
                for part in parts
            ]
            continue

        # First group when the pattern defines one, else the whole match.
        capture = 1 if pattern.groups >= 1 else 0
        new_parts: list[dict] = []
        for part in parts:
            if part["kind"] == "block":
                new_parts.append(part)
                continue
            value = part["text"]
            last = 0
            for match in pattern.finditer(value):
                if match.start() > last:
                    new_parts.append({"kind": "text", "text": value[last:match.start()]})
                try:
                    content = match.group(capture)
                except (IndexError, re.error):
                    content = match.group(0)
                new_parts.append({"kind": "block", "text": content or "", "title": item["name"]})
                last = match.end()
            if last < len(value):
                new_parts.append({"kind": "text", "text": value[last:]})
        parts = new_parts
    return parts


def _parts_to_segments(parts: list[dict]) -> list[dict]:
    segments: list[dict] = []
    block_index = 0
    for part in parts:
        if part["kind"] == "block":
            content = (part["text"] or "").strip()
            if not content:
                continue
            segments.append({
                "type": "block",
                "html": escape_html(content),
                "title": part.get("title") or "Block",
                "id": f"block-{block_index}",
            })
            block_index += 1
        elif part["text"].strip():
            segments.append({"type": "text", "content": part["text"]})
    return segments


async def apply_to_display_messages(messages: list[dict], scripts: list[dict]) -> None:
    """Transform display segments in place (display-side scripts only)."""
    scripts = [s for s in scripts if s.get("apply_display")]
    if not scripts:
        return
    for index, depth in _real_depths(messages).items():
        message = messages[index]
        windowed = [s for s in scripts if in_window(s, depth)]
        if not windowed:
            continue
        segments = message.get("segments")
        if not segments:
            continue
        placement = "user" if message.get("role") == "user" else "ai"
        content_scripts = for_placement(windowed, placement)
        reasoning_scripts = for_placement(windowed, "reasoning")
        if not content_scripts and not reasoning_scripts:
            continue

        if content_scripts:
            compiled = _compiled(content_scripts)
            if compiled:
                new_segments = []
                for segment in segments:
                    if segment.get("type") != "text":
                        new_segments.append(segment)
                        continue
                    text = segment.get("content") or ""
                    if not text:
                        continue
                    if len(text) > MAX_INPUT_LENGTH:
                        text = text[:MAX_INPUT_LENGTH]
                    try:
                        parts = await asyncio.wait_for(
                            asyncio.to_thread(_split_sync, text, compiled),
                            timeout=REGEX_TIMEOUT,
                        )
                    except Exception:
                        parts = [{"kind": "text", "text": text}]
                    new_segments.extend(_parts_to_segments(parts))
                segments = new_segments
                message["segments"] = segments

        if reasoning_scripts:
            for segment in segments:
                if segment.get("type") == "reasoning" and segment.get("html"):
                    raw = html.unescape(segment["html"])
                    segment["html"] = escape_html(await apply_text(raw, reasoning_scripts))


def preview_transform(
    pattern: str,
    replacement: str,
    flags: str,
    sample: str,
    as_block: bool = False,
    name: str = "Block",
) -> str:
    """Render one script against a sample as readable text (blocks delimited)."""
    compiled_pattern = compile_pattern(pattern, flags)
    if compiled_pattern is None:
        raise ValueError("pattern does not compile")
    item = {
        "pattern": compiled_pattern,
        "replacement": replacement,
        "as_block": as_block,
        "name": name or "Block",
    }
    out: list[str] = []
    for part in _split_sync(sample, [item]):
        if part["kind"] == "block":
            title = part.get("title") or "Block"
            out.append(f"[{title}]\n{part['text'].strip()}\n[/{title}]")
        else:
            out.append(part["text"])
    return "".join(out)
