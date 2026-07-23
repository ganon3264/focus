from __future__ import annotations

from contextlib import asynccontextmanager

import aiosqlite

from focus.core.paths import DB_PATH


@asynccontextmanager
async def _db_conn(db: aiosqlite.Connection | None = None):
    """Yield *db* if provided, otherwise open and close a fresh connection."""
    if db is not None:
        yield db
    else:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("PRAGMA foreign_keys=ON")
            yield conn
