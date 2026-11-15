from __future__ import annotations

import json

import aiosqlite

from focus.core.prefs import normalize
from focus.db.settings import delete_setting, upsert_setting

PREFS_KEY = "prefs"


async def load_prefs(db: aiosqlite.Connection) -> dict:
    async with db.execute("SELECT value FROM settings WHERE key = ?", (PREFS_KEY,)) as cur:
        row = await cur.fetchone()
    stored = None
    if row:
        try:
            stored = json.loads(row["value"])
        except (TypeError, ValueError):
            stored = None
    return normalize(stored)


async def save_prefs(db: aiosqlite.Connection, patch: dict) -> dict:
    current = await load_prefs(db)
    merged = {**current, **(patch if isinstance(patch, dict) else {})}
    prefs = normalize(merged)
    await upsert_setting(db, PREFS_KEY, json.dumps(prefs))
    await db.commit()
    return prefs


async def reset_prefs(db: aiosqlite.Connection) -> dict:
    await delete_setting(db, PREFS_KEY)
    await db.commit()
    return normalize(None)
