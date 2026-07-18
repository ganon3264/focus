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
