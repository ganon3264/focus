import os
import shutil
import tempfile

import aiosqlite
import httpx
import pytest


@pytest.fixture
async def client():
    """Create an async HTTP client with a fresh isolated database per test."""
    tmpdir = tempfile.mkdtemp()
    path = os.path.join(tmpdir, "test.db")
    backups_dir = os.path.join(tmpdir, "backups")
    os.makedirs(backups_dir, exist_ok=True)
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
    shutil.rmtree(tmpdir, ignore_errors=True)


async def create_character(client, name="Test Char", **overrides):
    body = {
        "name": name,
        "description": "Desc",
        "personality": "Neutral",
        "scenario": "Test",
        **overrides,
    }
    resp = await client.post("/api/characters/", json=body)
    assert resp.status_code == 201
    return resp.json()


async def create_persona(client, name="Test Persona", **overrides):
    body = {"name": name, "description": "A persona", **overrides}
    resp = await client.post("/api/personas/", json=body)
    assert resp.status_code == 201
    return resp.json()


async def create_preset(client, name="Test Preset"):
    resp = await client.post("/api/presets/", data={"name": name})
    assert resp.status_code == 201
    return resp.json()


async def create_chat(client, character_id=None, persona_id=None, preset_id=None, title="Test Chat"):
    body = {"title": title}
    if character_id:
        body["character_id"] = character_id
    if persona_id:
        body["persona_id"] = persona_id
    if preset_id:
        body["preset_id"] = preset_id
    resp = await client.post("/api/chats/", json=body)
    assert resp.status_code == 201
    return resp.json()
