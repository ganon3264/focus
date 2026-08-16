from __future__ import annotations

import json


def render_message_segments(
    content: str,
    variant_meta: str | None = None,
    segments_json: str | None = None,
) -> list[dict]:
    """Split message content into typed segments for template rendering.

    If *segments_json* is provided (from the stored ``segments_json`` column),
    it is parsed and returned directly.  Otherwise a legacy fallback builds
    segments from ``variant_meta`` reasoning plus the plain ``content`` text.

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

    try:
        vm = json.loads(variant_meta) if variant_meta else {}
    except (TypeError, ValueError):
        vm = {}
    reasoning_text = vm.get("reasoning") if isinstance(vm, dict) else None
    if reasoning_text:
        escaped = escape_html(reasoning_text.strip())
        segments.append({"type": "reasoning", "html": escaped, "index": 0})

    if content and content.strip():
        segments.append({"type": "text", "content": content})

    return segments


def escape_html(text: str) -> str:
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text
