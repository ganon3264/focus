import logging
from datetime import datetime, timezone

import aiosqlite

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
IMAGE_TOKEN_ESTIMATE = 85
AUDIO_TOKEN_ESTIMATE = 100

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
