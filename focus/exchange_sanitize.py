"""Security helpers for the .focus archive format.

These functions validate and normalize content coming from untrusted
archives before it reaches the filesystem or the database.
"""

import html
import json
from pathlib import Path

from focus.core.message_render import escape_html

MAX_IMPORT_ENTRIES = 10000
MAX_IMPORT_UNCOMPRESSED_BYTES = 512 * 1024 * 1024


def is_safe_zip_entry(name: str) -> bool:
    """Reject absolute paths, backslashes, and ``..`` traversal."""
    if not name or name.startswith("/") or "\\" in name:
        return False
    return ".." not in Path(name).parts


def sanitize_tool_calls(raw) -> list[dict]:
    """Restrict tool-call dicts to the shapes the templates expect."""
    out: list[dict] = []
    if isinstance(raw, list):
        for tc in raw:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function")
            if not isinstance(fn, dict):
                continue
            name = fn.get("name")
            args = fn.get("arguments")
            if not isinstance(name, str) or not isinstance(args, str):
                continue
            call = {
                "id": tc.get("id") if isinstance(tc.get("id"), str) else "",
                "type": "function",
                "function": {"name": name, "arguments": args},
            }
            result = tc.get("result")
            if isinstance(result, str):
                call["result"] = result
            is_error = tc.get("is_error")
            if isinstance(is_error, bool):
                call["is_error"] = is_error
            image_url = tc.get("image_url")
            if isinstance(image_url, str):
                call["image_url"] = image_url
            out.append(call)
    return out


def sanitize_segments_json(segments_json) -> str | None:
    """Normalize stored segments to the shapes the app itself produces.

    Reasoning ``html`` is pre-escaped by the app's builder
    (``focus.core.segments``), so imported html is re-escaped to make the
    template's ``| safe`` rendering safe for archive-controlled content.
    Returns ``None`` when the payload is unusable.
    """
    if not segments_json:
        return None
    try:
        segments = json.loads(segments_json)
    except (TypeError, ValueError):
        return None
    if not isinstance(segments, list):
        return None
    out: list[dict] = []
    for seg in segments:
        if not isinstance(seg, dict):
            continue
        stype = seg.get("type")
        if stype == "text":
            content = seg.get("content")
            if isinstance(content, str):
                out.append({"type": "text", "content": content})
        elif stype == "reasoning":
            raw_html = seg.get("html")
            if isinstance(raw_html, str):
                index = seg.get("index")
                out.append({
                    "type": "reasoning",
                    "html": escape_html(html.unescape(raw_html)),
                    "index": index if isinstance(index, int) else 0,
                })
        elif stype == "tool_boundary":
            out.append({"type": "tool_boundary", "tool_calls": sanitize_tool_calls(seg.get("tool_calls"))})
    return json.dumps(out) if out else None
