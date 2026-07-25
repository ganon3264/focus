from __future__ import annotations

import base64
import json
import logging
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image

from focus.core.media import image_format_var
from focus.core.paths import ASSETS_DIR, TOOL_ASSETS_DIR

logger = logging.getLogger("focus.core.tool_media")


def _format_ext(fmt: str) -> str:
    return "png" if fmt == "png" else "webp"


def _format_mime(fmt: str) -> str:
    return "image/png" if fmt == "png" else "image/webp"


def persist_tool_image(data_url: str) -> str | None:
    """Extract base64 image data from a data: URL, write to TOOL_ASSETS_DIR
    in the format specified by ``image_format``, return the relative path
    (e.g. ``tool/<uuid>.webp``).

    Returns ``None`` if *data_url* is not a ``data:`` URL.
    """
    if not data_url.startswith("data:"):
        return None
    header, b64_data = data_url.split(",", 1)
    raw = base64.b64decode(b64_data)

    fmt = image_format_var.get()
    ext = _format_ext(fmt)
    mime = _format_mime(fmt)

    source_mime = header.split(";")[0].split(":")[1] if ":" in header else ""
    if source_mime != mime:
        img = Image.open(BytesIO(raw))
        buf = BytesIO()
        if fmt == "png":
            img.save(buf, format="PNG", optimize=True)
        else:
            img.save(buf, format="WEBP", quality=85)
        raw = buf.getvalue()

    file_name = f"{uuid.uuid4()}.{ext}"
    rel_path = f"tool/{file_name}"
    TOOL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    (TOOL_ASSETS_DIR / file_name).write_bytes(raw)
    return rel_path


def load_tool_image_data_url(rel_path: str) -> str | None:
    """Read a tool-result image from ``ASSETS_DIR / rel_path`` and return a
    data: URL for use in API payloads, re-encoding to the current
    ``image_format`` if necessary.  The converted copy is cached on disk
    so subsequent loads skip re-encoding.

    Returns ``None`` if the file is missing.
    """
    fmt = image_format_var.get()
    ext = _format_ext(fmt)
    mime = _format_mime(fmt)

    stem = Path(rel_path).stem
    cached_path = ASSETS_DIR / f"tool/{stem}.{ext}"
    if cached_path.exists():
        data = cached_path.read_bytes()
        return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"

    orig_path = ASSETS_DIR / rel_path
    if not orig_path.exists():
        logger.warning("Tool image not found: %s", orig_path)
        return None

    data = orig_path.read_bytes()
    img = Image.open(BytesIO(data))
    buf = BytesIO()
    if fmt == "png":
        img.save(buf, format="PNG", optimize=True)
    else:
        img.save(buf, format="WEBP", quality=85)
    converted = buf.getvalue()

    cached_path.parent.mkdir(parents=True, exist_ok=True)
    cached_path.write_bytes(converted)
    return f"data:{mime};base64,{base64.b64encode(converted).decode('ascii')}"


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
