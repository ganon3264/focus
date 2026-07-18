import os
import shutil
import uuid
from pathlib import Path

import aiosqlite
import httpx
import pytest


@pytest.fixture
def tmp_test_dir():
    path = Path("tests/tmp") / f"test_{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    yield str(path)
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
async def client(tmp_test_dir):
    """Create an async HTTP client with a fresh isolated database per test."""
    path = os.path.join(tmp_test_dir, "test.db")
    backups_dir = os.path.join(tmp_test_dir, "backups")
    os.makedirs(backups_dir, exist_ok=True)
    old_backups = os.environ.get("FOCUS_BACKUPS_DIR")
    os.environ["FOCUS_BACKUPS_DIR"] = backups_dir

    from focus.core.database import SCHEMA

    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(SCHEMA)

    from focus.core.database import get_db
    from main import app

    async def override_get_db():
        async with aiosqlite.connect(path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys=ON")
            yield conn

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
    if old_backups is None:
        os.environ.pop("FOCUS_BACKUPS_DIR", None)
    else:
        os.environ["FOCUS_BACKUPS_DIR"] = old_backups
