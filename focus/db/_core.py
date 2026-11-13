from __future__ import annotations

from contextlib import asynccontextmanager

import aiosqlite

from focus.core.database import open_db


@asynccontextmanager
async def _db_conn(db: aiosqlite.Connection | None = None):
    """Yield *db* if provided, otherwise open and close a fresh connection."""
    if db is not None:
        yield db
    else:
        async with open_db() as conn:
            yield conn
