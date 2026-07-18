import asyncio
import base64
import logging
import math
import time
from datetime import datetime, timezone
from io import BytesIO

import aiosqlite
from PIL import Image

logger = logging.getLogger("focus.utils")

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
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 1.0
OPENAI_HTTP_TIMEOUT = 120.0
GOOGLE_VERTEX_HTTP_TIMEOUT = 300.0
GOOGLE_VERTEX_HTTP_RETRIES = 3
MODEL_FETCH_HTTP_TIMEOUT = 10.0

# ── Caching ───────────────────────────────────────────────────────────────────
MODEL_CACHE_TTL = 300


class TTLCache:
    """Async-safe TTL cache with dict semantics.

    Two access patterns:
      get(key) / set(key, value)  — standard read-through (returns None on miss/expiry)
      get_or_refresh(key, factory) — atomic check-and-fetch (factory is async, called
                                     outside the lock to avoid blocking concurrent reads)
    """

    def __init__(self, ttl: int = MODEL_CACHE_TTL):
        self._data: dict[str, object] = {}
        self._times: dict[str, float] = {}
        self._lock = asyncio.Lock()
        self._ttl = ttl

    async def get(self, key: str):
        """Return cached value if fresh, else None."""
        async with self._lock:
            ts = self._times.get(key, 0.0)
            if key in self._data and time.monotonic() - ts < self._ttl:
                return self._data[key]
            return None

    async def set(self, key: str, value):
        """Store value with current timestamp."""
        async with self._lock:
            self._data[key] = value
            self._times[key] = time.monotonic()

    async def get_or_refresh(self, key: str, factory):
        """Return fresh value or call async factory() to populate.

        If stale/missing, releases the lock during IO (factory),
        then stores the result.  Concurrent callers may both fetch,
        but last-writer-wins on set.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached
        new_value = await factory()
        if new_value is not None:
            await self.set(key, new_value)
        return new_value

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
