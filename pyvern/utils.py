import base64
import logging
import math
from datetime import datetime, timezone
from io import BytesIO

import aiosqlite
from PIL import Image

logger = logging.getLogger("pyvern.utils")

SUFFIX_MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".gif": "image/gif", ".webp": "image/webp", ".mp3": "audio/mpeg",
    ".wav": "audio/wav", ".ogg": "audio/ogg",
}

SUFFIX_MIME_MAP_IMAGES_ONLY = {k: v for k, v in SUFFIX_MIME_MAP.items() if v.startswith("image/")}

THINK_OPEN = "<think>\n"
THINK_CLOSE = "\n</think>\n\n"
THOUGHT_SIGNATURE_OPEN = "<thought_signature>"
THOUGHT_SIGNATURE_CLOSE = "</thought_signature>"

DEFAULT_OPENAI_COMPAT_BASE_URL = "http://localhost:8080/v1"

# ── Provider defaults ────────────────────────────────────────────────────────
DEFAULT_MAX_TOKENS = 1024
DEFAULT_TEMPERATURE = 1.0
OPENAI_HTTP_TIMEOUT = 120.0
GOOGLE_VERTEX_HTTP_TIMEOUT = 300.0
GOOGLE_VERTEX_HTTP_RETRIES = 3
MODEL_FETCH_HTTP_TIMEOUT = 10.0

# ── Caching ───────────────────────────────────────────────────────────────────
MODEL_CACHE_TTL = 300

# ── Token estimation ──────────────────────────────────────────────────────────
AUDIO_TOKEN_ESTIMATE = 100

def _image_dims_from_data_url(url: str) -> tuple[int, int] | None:
    """Extract (width, height) from a data: URL using Pillow."""
    try:
        _, encoded = url.split(",", 1)
        data = base64.b64decode(encoded)
        with Image.open(BytesIO(data)) as img:
            return img.width, img.height
    except Exception:
        return None

def estimate_image_tokens(width: int, height: int) -> int:
    """Gemini-style image token estimate.
    Both dimensions ≤384px: 258 tokens flat.
    Larger: ceil(w/768) × ceil(h/768) × 258.
    """
    if width <= 384 and height <= 384:
        return 258
    return math.ceil(width / 768) * math.ceil(height / 768) * 258

# ── Macro resolution ──────────────────────────────────────────────────────────
MACRO_MAX_PASSES = 10


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def resolve_secret_key(db: aiosqlite.Connection, api_key: str) -> str:
    if not api_key or not api_key.startswith("SECRET:"):
        return api_key
    secret_name = api_key[7:]
    try:
        async with db.execute("SELECT value FROM secrets WHERE name = ?", (secret_name,)) as cur:
            row = await cur.fetchone()
    except Exception as e:
        logger.warning("Failed to resolve secret %s: %s", secret_name, e)
        return ""
    return row["value"] if row else ""


def variable_group_name(block_name: str) -> str:
    return block_name.split(":")[0] if ":" in block_name else block_name
