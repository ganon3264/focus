from __future__ import annotations

import base64
import json
import logging
import uuid

from focus.core.paths import ASSETS_DIR, TOOL_ASSETS_DIR

logger = logging.getLogger("focus.core.tool_media")


def persist_tool_image(data_url: str) -> str | None:
    """Extract base64 image data from a data: URL, write to TOOL_ASSETS_DIR
    as WebP, return the relative path (e.g. ``tool/<uuid>.webp``).

    Returns ``None`` if *data_url* is not a ``data:`` URL.
    """
    if not data_url.startswith("data:"):
        return None
    _header, b64_data = data_url.split(",", 1)
    raw = base64.b64decode(b64_data)
    file_name = f"{uuid.uuid4()}.webp"
    rel_path = f"tool/{file_name}"
    TOOL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    (TOOL_ASSETS_DIR / file_name).write_bytes(raw)
    return rel_path


def load_tool_image_data_url(rel_path: str) -> str | None:
    """Read a tool-result image from ``ASSETS_DIR / rel_path`` and return a
    data: URL for use in API payloads.  Returns ``None`` if the file is missing.
    """
    img_path = ASSETS_DIR / rel_path
    if not img_path.exists():
        logger.warning("Tool image not found: %s", img_path)
        return None
    data = img_path.read_bytes()
    return f"data:image/webp;base64,{base64.b64encode(data).decode('ascii')}"


def tool_image_url(rel_path: str) -> str:
    """Return the ``/assets/...`` URL for frontend consumption."""
    return f"/assets/{rel_path}"


def extract_image_from_extra(extra_json: str | None) -> str | None:
    """Legacy — extract a data: URL from an ``extra_message_json`` blob.
    Only needed for old tool_calls rows that stored images inline.
    """
    if not extra_json:
        return None
    try:
        extra = json.loads(extra_json)
        content = extra.get("content", [])
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return part.get("image_url", {}).get("url")
    except (json.JSONDecodeError, TypeError):
        pass
    return None
