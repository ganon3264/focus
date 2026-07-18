import os

import aiosqlite
import pytest

from focus.backup import create_backup, delete_backup, list_backups, restore_backup
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

        backups = list_backups(backups_path=backups_path)
        assert len(backups) == 1
        assert backups[0]["id"] == result["id"]

    async def test_list_backups_empty(self, tmp_test_dir):
        backups_path = os.path.join(tmp_test_dir, "empty_backups")
        backups = list_backups(backups_path=backups_path)
        assert backups == []

    async def test_delete_backup(self, tmp_test_dir):
        db_path = os.path.join(tmp_test_dir, "focus.db")
        os.makedirs(os.path.join(tmp_test_dir, "assets"), exist_ok=True)
        backups_path = os.path.join(tmp_test_dir, "backups")

        await _init_temp_db(db_path)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            result = await create_backup(db, backups_path=backups_path)

        assert len(list_backups(backups_path=backups_path)) == 1
        delete_backup(result["id"], backups_path=backups_path)
        assert len(list_backups(backups_path=backups_path)) == 0

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
            delete_backup("nonexistent", backups_path=backups_path)


class TestBackupAPI:
    async def test_create_backup_endpoint(self, client):
        resp = await client.post("/api/backups")
        assert resp.status_code == 201
        data = resp.json()
        assert data["size_bytes"] > 0

    async def test_list_backups_endpoint(self, client):
        await client.post("/api/backups")
        resp = await client.get("/api/backups")
        assert resp.status_code == 200
        backups = resp.json()
        assert len(backups) >= 1

    async def test_delete_backup_endpoint(self, client):
        resp = await client.post("/api/backups")
        backup_id = resp.json()["id"]

        del_resp = await client.delete(f"/api/backups/{backup_id}")
        assert del_resp.status_code == 204

    async def test_restore_backup_endpoint(self, client):
        await client.post("/api/backups")

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
