import json
import os

import aiosqlite
import pytest

from focus.backup import create_backup, delete_backup, get_backups_dir, list_backups, restore_backup
from focus.core.database import SCHEMA


async def _init_temp_db(db_path: str):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        await db.executescript(SCHEMA)
        await db.commit()


async def _count_chars(db_path: str) -> int:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) as c FROM characters") as cur:
            return (await cur.fetchone())["c"]


def _sse_events(text: str) -> list[dict]:
    events = []
    for block in text.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


async def _create_backup(client) -> dict:
    resp = await client.post("/api/backups")
    assert resp.status_code == 200
    done = [e for e in _sse_events(resp.text) if e["type"] == "done"]
    assert done, resp.text
    return done[-1]["result"]


class TestBackupFunctions:
    async def test_create_and_list_backup(self, tmp_test_dir):
        db_path = os.path.join(tmp_test_dir, "focus.db")
        os.makedirs(os.path.join(tmp_test_dir, "assets", "characters"), exist_ok=True)
        backups_path = os.path.join(tmp_test_dir, "backups")

        await _init_temp_db(db_path)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            result = await create_backup(db, backups_path=backups_path)

        assert result["size_bytes"] > 0
        assert "id" in result
        assert os.path.join(backups_path, result["id"] + ".focus")

        backups = await list_backups(backups_path=backups_path)
        assert len(backups) == 1
        assert backups[0]["id"] == result["id"]

    async def test_list_backups_empty(self, tmp_test_dir):
        backups_path = os.path.join(tmp_test_dir, "empty_backups")
        backups = await list_backups(backups_path=backups_path)
        assert backups == []

    async def test_delete_backup(self, tmp_test_dir):
        db_path = os.path.join(tmp_test_dir, "focus.db")
        os.makedirs(os.path.join(tmp_test_dir, "assets"), exist_ok=True)
        backups_path = os.path.join(tmp_test_dir, "backups")

        await _init_temp_db(db_path)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            result = await create_backup(db, backups_path=backups_path)

        assert len(await list_backups(backups_path=backups_path)) == 1
        await delete_backup(result["id"], backups_path=backups_path)
        assert len(await list_backups(backups_path=backups_path)) == 0

    async def test_restore_imports_data(self, tmp_test_dir):
        db_path = os.path.join(tmp_test_dir, "focus.db")
        os.makedirs(os.path.join(tmp_test_dir, "assets"), exist_ok=True)
        backups_path = os.path.join(tmp_test_dir, "backups")

        await _init_temp_db(db_path)

        # Insert a character
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute(
                "INSERT INTO characters (id, name, image_path, card_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (
                    "aaa",
                    "Alice",
                    None,
                    '{"data":{"name":"Alice"}}',
                    "2024-01-01T00:00:00+00:00",
                ),
            )
            await db.commit()
            result = await create_backup(db, backups_path=backups_path)

        assert await _count_chars(db_path) == 1

        # Restore (imports a duplicate with new IDs)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            restore_result = await restore_backup(result["id"], db, backups_path=backups_path)
            assert restore_result["restored"] is True
            assert restore_result["imported"]["characters"] >= 1

        # Now there should be 2 characters (original + imported)
        assert await _count_chars(db_path) == 2

    async def test_restore_nonexistent_backup(self, tmp_test_dir):
        db_path = os.path.join(tmp_test_dir, "focus.db")
        await _init_temp_db(db_path)
        backups_path = os.path.join(tmp_test_dir, "empty_backups")
        os.makedirs(backups_path, exist_ok=True)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            with pytest.raises(FileNotFoundError):
                await restore_backup("nonexistent", db, backups_path=backups_path)

    async def test_delete_nonexistent_backup(self, tmp_test_dir):
        backups_path = os.path.join(tmp_test_dir, "empty_backups")
        with pytest.raises(FileNotFoundError):
            await delete_backup("nonexistent", backups_path=backups_path)


class TestBackupAPI:
    async def test_create_backup_endpoint(self, client):
        resp = await client.post("/api/backups")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _sse_events(resp.text)
        progress = [e for e in events if e["type"] == "progress"]
        assert any(e["label"] == "Reading database" for e in progress)
        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1
        assert done[0]["result"]["size_bytes"] > 0

    async def test_list_backups_endpoint(self, client):
        await _create_backup(client)
        resp = await client.get("/api/backups")
        assert resp.status_code == 200
        backups = resp.json()
        assert len(backups) >= 1

    async def test_delete_backup_endpoint(self, client):
        backup = await _create_backup(client)

        del_resp = await client.delete(f"/api/backups/{backup['id']}")
        assert del_resp.status_code == 204

    async def test_restore_backup_endpoint(self, client):
        await _create_backup(client)

        backups = (await client.get("/api/backups")).json()
        backup_id = backups[0]["id"]

        resp = await client.post(f"/api/backups/{backup_id}/restore")
        assert resp.status_code == 200
        assert resp.json()["restored"] is True

    async def test_restore_nonexistent_backup_endpoint(self, client):
        resp = await client.post("/api/backups/nonexistent/restore")
        assert resp.status_code == 404

    async def test_delete_nonexistent_backup_endpoint(self, client):
        resp = await client.delete("/api/backups/nonexistent")
        assert resp.status_code == 404


class TestCleanEndpoint:
    async def test_streams_stages_then_counts(self, client):
        char = await client.post("/api/characters", json={"name": "Trashed"})
        assert char.status_code == 201
        await client.delete(f"/api/characters/{char.json()['id']}")

        resp = await client.post("/api/db/clean")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        events = _sse_events(resp.text)
        labels = [e["label"] for e in events if e["type"] == "progress"]
        assert labels[0] == "Trashed chats"
        assert "Orphaned files" in labels
        assert labels[-1] == "Vacuumed"

        done = [e for e in events if e["type"] == "done"]
        assert len(done) == 1
        assert done[0]["result"]["characters"] == 1


class TestGetBackupsDir:
    def test_default_derives_from_data_dir(self, monkeypatch, tmp_path):
        import focus.backup as backup

        monkeypatch.delenv("FOCUS_BACKUPS_DIR", raising=False)
        monkeypatch.setattr(backup, "DATA_DIR", tmp_path)
        assert get_backups_dir() == tmp_path / "backups"

    def test_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FOCUS_BACKUPS_DIR", str(tmp_path / "from_env"))
        assert get_backups_dir() == tmp_path / "from_env"

    def test_explicit_root_wins_over_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("FOCUS_BACKUPS_DIR", str(tmp_path / "from_env"))
        assert get_backups_dir(str(tmp_path / "explicit")) == tmp_path / "explicit"
