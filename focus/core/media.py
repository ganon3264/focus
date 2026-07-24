from __future__ import annotations

import asyncio
import base64
import logging
from io import BytesIO
from pathlib import Path

from PIL import Image

from focus.core.paths import COMPRESSED_DIR

logger = logging.getLogger("focus.core.media")

MAX_IMAGE_B64 = int(3.5 * 1024 * 1024)
MAX_IMAGE_DIMENSION = 1568


async def ensure_compressed(orig_path: str, mime: str) -> tuple[Path, str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, ensure_compressed_sync, orig_path, mime)


def ensure_compressed_sync(orig_path: str, mime: str) -> tuple[Path, str]:
    """Return (compressed_file_path, output_mime) from a disk cache.

    Creates a compressed WebP version on disk if missing or stale.
    Caps the longest edge at MAX_IMAGE_DIMENSION before compressing.
    WebP natively handles alpha, so transparency is preserved without
    a separate PNG path. Cache invalidation is by mtime.
    """
    orig = Path(orig_path)
    stem = orig.stem
    webp_cache = COMPRESSED_DIR / f"{stem}.webp"

    try:
        orig_mtime = orig.stat().st_mtime
    except OSError:
        orig_mtime = 0

    if webp_cache.exists() and webp_cache.stat().st_mtime >= orig_mtime:
        return webp_cache, "image/webp"

    data = orig.read_bytes()

    if len(base64.b64encode(data).decode()) <= MAX_IMAGE_B64:
        out_path = COMPRESSED_DIR / f"{stem}{Path(orig_path).suffix or '.png'}"
        out_path.write_bytes(data)
        return out_path, mime

    img = Image.open(BytesIO(data))

    longest = max(img.width, img.height)
    if longest > MAX_IMAGE_DIMENSION:
        scale = MAX_IMAGE_DIMENSION / longest
        w = max(1, int(img.width * scale))
        h = max(1, int(img.height * scale))
        img = img.resize((w, h), Image.LANCZOS)

    for quality in (80, 65, 50, 35, 20):
        scale = 1.0
        while scale > 0.05:
            scale *= 0.75
            w = max(1, int(img.width * scale))
            h = max(1, int(img.height * scale))
            resized = img.resize((w, h), Image.LANCZOS)
            buf = BytesIO()
            resized.save(buf, format="WEBP", quality=quality)
            if len(base64.b64encode(buf.getvalue()).decode()) <= MAX_IMAGE_B64:
                webp_cache.write_bytes(buf.getvalue())
                return webp_cache, "image/webp"

    webp_cache.write_bytes(buf.getvalue())
    return webp_cache, "image/webp"


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
        compressed_path, out_mime = await ensure_compressed(path, mime)
        data = compressed_path.read_bytes()
    except OSError as e:
        logger.warning("load_media: compression failed for %s: %s", path, e)
        return None

    return {
        "type": "image_url",
        "image_url": {"url": f"data:{out_mime};base64,{base64.b64encode(data).decode()}"},
    }
