from __future__ import annotations

import asyncio
import base64
import contextvars
import hashlib
import logging
import uuid
from io import BytesIO
from pathlib import Path

from PIL import Image

from focus.core.paths import ASSETS_DIR, COMPRESSED_DIR, TOOL_ASSETS_DIR
from focus.core.utils import SUFFIX_MIME_MAP

logger = logging.getLogger("focus.media")

MAX_IMAGE_B64 = int(3.5 * 1024 * 1024)
MAX_IMAGE_DIMENSION = 1568

image_format_var = contextvars.ContextVar("image_format", default="webp")


def set_image_format(fmt: str) -> None:
    image_format_var.set(fmt)


def mime_for(fmt: str) -> str:
    if fmt == "png":
        return "image/png"
    if fmt == "jpeg":
        return "image/jpeg"
    return "image/webp"


def ext_for(fmt: str) -> str:
    if fmt == "png":
        return "png"
    if fmt == "jpeg":
        return "jpg"
    return "webp"


def _flatten_alpha(img: Image.Image) -> Image.Image:
    """Composite alpha onto white so alpha-capable modes can be saved as JPEG."""
    if img.mode == "RGB":
        return img
    if img.mode == "RGBA" or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    return img.convert("RGB")


def compress_image(data: bytes, target_format: str) -> bytes:
    """Compress image bytes in memory to *target_format* (png/jpeg/webp).

    Detects the source format from content, caps the longest edge at
    MAX_IMAGE_DIMENSION, and degrades quality/scale until the base64 payload
    fits MAX_IMAGE_B64. Alpha is flattened (on white) for JPEG. Pure function:
    no disk I/O, no caching.
    """
    fmt = target_format if target_format in ("png", "jpeg", "webp") else "webp"

    img = Image.open(BytesIO(data))

    longest = max(img.width, img.height)
    if longest > MAX_IMAGE_DIMENSION:
        scale = MAX_IMAGE_DIMENSION / longest
        w = max(1, int(img.width * scale))
        h = max(1, int(img.height * scale))
        img = img.resize((w, h), Image.LANCZOS)

    if fmt == "png":
        buf = BytesIO()
        img.save(buf, format="PNG", optimize=True)
        if len(base64.b64encode(buf.getvalue()).decode()) <= MAX_IMAGE_B64:
            return buf.getvalue()
        scale = 1.0
        while scale > 0.05:
            scale *= 0.75
            w = max(1, int(img.width * scale))
            h = max(1, int(img.height * scale))
            resized = img.resize((w, h), Image.LANCZOS)
            buf = BytesIO()
            resized.save(buf, format="PNG", optimize=True)
            if len(base64.b64encode(buf.getvalue()).decode()) <= MAX_IMAGE_B64:
                return buf.getvalue()
        return buf.getvalue()

    if fmt == "jpeg":
        img = _flatten_alpha(img)

    for quality in (85, 80, 65, 50, 35, 20):
        scale = 1.0
        while True:
            w = max(1, int(img.width * scale))
            h = max(1, int(img.height * scale))
            resized = img if scale >= 1.0 else img.resize((w, h), Image.LANCZOS)
            buf = BytesIO()
            if fmt == "jpeg":
                resized.save(buf, format="JPEG", quality=quality)
            else:
                resized.save(buf, format="WEBP", quality=quality)
            if len(base64.b64encode(buf.getvalue()).decode()) <= MAX_IMAGE_B64:
                return buf.getvalue()
            if scale <= 0.05:
                break
            scale *= 0.75

    return buf.getvalue()


_MIME_SUFFIX = {v: k for k, v in SUFFIX_MIME_MAP.items()}


def persist_tool_image(data_url: str) -> str | None:
    """Store the raw image bytes from a ``data:`` URL under ``assets/tool/``
    and return the ASSETS_DIR-relative path (e.g. ``tool/<uuid>.png``).

    The original bytes are kept verbatim — conversion happens on read via
    ``get_compressed_image``. Returns ``None`` if *data_url* is not a ``data:``
    URL.
    """
    if not data_url.startswith("data:"):
        return None
    header, b64_data = data_url.split(",", 1)
    raw = base64.b64decode(b64_data)

    source_mime = header.split(";")[0].split(":")[1] if ":" in header else ""
    suffix = _MIME_SUFFIX.get(source_mime, ".png")

    file_name = f"{uuid.uuid4()}{suffix}"
    rel_path = f"tool/{file_name}"
    TOOL_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    (TOOL_ASSETS_DIR / file_name).write_bytes(raw)
    return rel_path


def _resolve_orig(rel_path: str) -> Path:
    """Resolve a stored path: DB rows use cwd-relative ``assets/...`` paths
    (attachments, avatars, blocks) or ASSETS_DIR-relative ``tool/...`` paths."""
    p = Path(rel_path)
    if p.exists():
        return p
    return ASSETS_DIR / rel_path


def _compressed_path_for(rel_path: str, target_format: str) -> Path:
    """Map an original asset to its compressed cache file, mirroring the
    ASSETS_DIR-relative path under COMPRESSED_DIR with the target ext."""
    try:
        mirror = _resolve_orig(rel_path).resolve().relative_to(ASSETS_DIR.resolve())
    except ValueError:
        digest = hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:16]
        mirror = Path(digest)
    return COMPRESSED_DIR / mirror.with_suffix(f".{ext_for(target_format)}")


def get_compressed_image(rel_path: str, target_format: str) -> tuple[bytes, str] | None:
    """Return (bytes, mime) for the asset at *rel_path* compressed to
    *target_format*, from a disk cache under ``assets/compressed/``.

    The cache key includes the target ext, so a format change simply produces
    a different cache file and the original is recompressed. The cache entry
    is regenerated when it is older than the original (avatars are replaced
    in place). Returns ``None`` if the original is missing.
    """
    orig = _resolve_orig(rel_path)
    if not orig.exists():
        logger.warning("Image not found: %s", orig)
        return None

    out_mime = mime_for(target_format)
    cache_path = _compressed_path_for(rel_path, target_format)

    try:
        if cache_path.exists() and cache_path.stat().st_mtime >= orig.stat().st_mtime:
            return cache_path.read_bytes(), out_mime
    except OSError:
        pass

    converted = compress_image(orig.read_bytes(), target_format)
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(converted)
    except OSError as e:
        logger.warning("Failed to write compressed cache %s: %s", cache_path, e)
    return converted, out_mime


async def get_compressed_image_async(
    rel_path: str, target_format: str | None = None,
) -> tuple[bytes, str] | None:
    """Executor-wrapped ``get_compressed_image`` (keeps image work off the loop)."""
    if target_format is None:
        target_format = image_format_var.get()
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, get_compressed_image, rel_path, target_format)


async def tool_image_data_url(rel_path: str) -> str | None:
    """Data: URL of a tool-result image compressed to the current format,
    for use in API payloads. Returns ``None`` if the file is missing."""
    result = await get_compressed_image_async(rel_path)
    if result is None:
        return None
    data, mime = result
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


def tool_image_url(rel_path: str) -> str:
    """Return the ``/assets/...`` URL for frontend consumption."""
    return f"/assets/{rel_path}"


async def load_media(media_row: dict) -> dict | None:
    """Read a media file from disk and return an OpenAI-format block."""
    path = media_row.get("image_path") or media_row.get("file_path")
    if not path:
        logger.warning("load_media: no path in media_row %r", media_row.get("id"))
        return None
    if not Path(path).exists():
        logger.warning("load_media: file not found %s", path)
        return None

    mime = media_row.get("mime_type", "image/png")

    if mime.startswith("audio/"):
        try:
            data = Path(path).read_bytes()
        except OSError as e:
            logger.warning("load_media: cannot read %s: %s", path, e)
            return None
        fmt = mime.split("/")[-1].replace("mpeg", "mp3")
        return {
            "type": "input_audio",
            "input_audio": {"data": base64.b64encode(data).decode(), "format": fmt},
        }

    try:
        result = await get_compressed_image_async(path)
    except OSError as e:
        logger.warning("load_media: compression failed for %s: %s", path, e)
        return None
    if result is None:
        return None

    data, out_mime = result
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{out_mime};base64,{base64.b64encode(data).decode()}"},
    }
