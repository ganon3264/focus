from __future__ import annotations

import json
import re


def render_message_segments(
    content: str,
    reasoning: str | None = None,
    segments_json: str | None = None,
) -> list[dict]:
    """Split message content into typed segments for template rendering.

    If *segments_json* is provided (from the stored ``segments_json`` column),
    it is parsed and returned directly.  Otherwise the legacy parsing path is
    used (``%%%TOOL_BOUNDARY%%%`` markers + ``<think>`` blocks in content).

    Returns a flat list of dicts:
      {"type": "text", "content": str}          # raw text (markdown-processed by JS later)
      {"type": "reasoning", "html": str, "index": int}  # pre-escaped HTML
      {"type": "tool_boundary"}                  # split point for tool calls

    Reasoning blocks get sequential indices; the first (index 0) has no
    individual toggle — it's controlled by the message-level reasoning button.
    Subsequent blocks get a clickable toggle button.
    """
    if segments_json:
        return json.loads(segments_json)

    segments: list[dict] = []
    reasoning_idx = 0

    if reasoning:
        escaped = _escape_html(reasoning.strip())
        segments.append({"type": "reasoning", "html": escaped, "index": 0})
        reasoning_idx = 1

    parts = content.split("%%%TOOL_BOUNDARY%%%")

    for pi, part in enumerate(parts):

        reasoning_idx = _extract_think_blocks(part, reasoning_idx, segments)

        text = strip_think_blocks(part)
        if text.strip():
            segments.append({"type": "text", "content": text})

        if pi < len(parts) - 1:
            segments.append({"type": "tool_boundary"})

    return segments


def _extract_think_blocks(text: str, start_idx: int, segments: list) -> int:
    """Find <think>...</think> blocks, add reasoning segments, return next index."""
    if not text:
        return start_idx

    code_blocks: list[str] = []
    protected = _protect_code(text, code_blocks)

    protected = re.sub(
        r"<thought_signature>[\s\S]*?(?:</thought_signature>|$)", "", protected
    )

    idx = start_idx
    for match in re.finditer(r"<think>([\s\S]*?)(?:</think>|$)", protected):
        raw = match.group(1)
        for j, cb in enumerate(code_blocks):
            raw = raw.replace(f"%%%FOCUS_CODE_{j}%%%", cb)
        escaped = _escape_html(raw).strip()
        segments.append({"type": "reasoning", "html": escaped, "index": idx})
        idx += 1

    return idx


def strip_think_blocks(text: str) -> str:
    """Remove <think>...</think> and <thought_signature> from text."""
    if not text:
        return ""
    result = re.sub(r"<think>[\s\S]*?(?:</think>|$)", "", text)
    result = re.sub(r"<thought_signature>[\s\S]*?(?:</thought_signature>|$)", "", result)
    return result


def _protect_code(text: str, stash: list) -> str:
    """Replace fenced and inline code blocks with markers."""
    text = re.sub(
        r"```[\s\S]*?(?:```|$)",
        lambda m: _stash(m.group(0), stash),
        text,
    )
    text = re.sub(
        r"`[^`\n]*`",
        lambda m: _stash(m.group(0), stash),
        text,
    )
    return text


def _stash(text: str, stash: list) -> str:
    idx = len(stash)
    stash.append(text)
    return f"%%%FOCUS_CODE_{idx}%%%"


def _escape_html(text: str) -> str:
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text
