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

DESTINATIONS_PROMPT = ("ephemeral",)
DESTINATIONS_DISPLAY = ("ephemeral", "cosmetic")

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


def _compiled(scripts: list[dict]) -> list[tuple]:
    out = []
    for script in scripts:
        # Draft rows (no pattern yet) must never run: an empty regex matches
        # everywhere and would splice the replacement into every position.
        if not (script.get("pattern") or "").strip():
            continue
        pattern = compile_pattern(script.get("pattern") or "", script.get("flags") or "")
        if pattern is not None:
            out.append((pattern, script.get("replacement") or ""))
    return out


def _apply_sync(text: str, compiled: list[tuple]) -> str:
    for pattern, replacement in compiled:
        text = pattern.sub(replacement, text)
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
    """Transform macro-resolved history in place (ephemeral scripts only)."""
    scripts = [s for s in scripts if s.get("destination") in DESTINATIONS_PROMPT]
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


async def apply_to_display_messages(messages: list[dict], scripts: list[dict]) -> None:
    """Transform display segments in place (ephemeral + cosmetic scripts)."""
    scripts = [s for s in scripts if s.get("destination") in DESTINATIONS_DISPLAY]
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
        for segment in segments:
            seg_type = segment.get("type")
            if seg_type == "text" and content_scripts:
                segment["content"] = await apply_text(segment.get("content"), content_scripts)
            elif seg_type == "reasoning" and reasoning_scripts and segment.get("html"):
                raw = html.unescape(segment["html"])
                segment["html"] = escape_html(await apply_text(raw, reasoning_scripts))
