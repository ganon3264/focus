from __future__ import annotations

import json


def render_message_segments(
    content: str,
    reasoning: str | None = None,
    segments_json: str | None = None,
) -> list[dict]:
    """Split message content into typed segments for template rendering.

    If *segments_json* is provided (from the stored ``segments_json`` column),
    it is parsed and returned directly.  Otherwise the legacy parsing path is
    used (``%%%TOOL_BOUNDARY%%%`` markers).

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

    if reasoning:
        escaped = escape_html(reasoning.strip())
        segments.append({"type": "reasoning", "html": escaped, "index": 0})

    parts = content.split("%%%TOOL_BOUNDARY%%%")

    for pi, part in enumerate(parts):
        if part.strip():
            segments.append({"type": "text", "content": part})

        if pi < len(parts) - 1:
            segments.append({"type": "tool_boundary"})

    return segments


def escape_html(text: str) -> str:
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text
