import shutil
import uuid
from pathlib import Path

import aiosqlite
import pytest

from focus.core.database import SCHEMA
from focus.core.paths import (
    ATTACHMENTS_DIR,
    BLOCKS_DIR,
    CHARACTERS_DIR,
    COMPRESSED_DIR,
    PERSONAS_DIR,
    PRESETS_DIR,
)
from focus.db.cleanup import clean_database, clean_orphaned_assets


@pytest.fixture(autouse=True)
def _clean_asset_subdirs():
    for d in [CHARACTERS_DIR, PERSONAS_DIR, PRESETS_DIR, ATTACHMENTS_DIR, BLOCKS_DIR]:
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
async def db(tmp_test_dir):
    path = Path(tmp_test_dir) / "test.db"
    conn = await aiosqlite.connect(str(path))
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    yield conn
    await conn.close()


def _char_id() -> str:
    return str(uuid.uuid4())


def _uuid_dir(parent: Path) -> Path:
    d = parent / str(uuid.uuid4())
    d.mkdir(parents=True, exist_ok=True)
    return d


class TestCleanOrphanedAssets:
    # ── Known files are kept ──

    async def test_keeps_known_character_avatar(self, db):
        cid = _char_id()
        char_dir = CHARACTERS_DIR / cid
        char_dir.mkdir(parents=True, exist_ok=True)
        path = str(char_dir / "avatar.png")
        Path(path).write_bytes(b"avatar")
        await db.execute(
            "INSERT INTO characters (id, name, image_path, card_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (cid, "Test", path, "{}", "now"),
        )
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert Path(path).exists()
        assert result["orphaned_files"] == 0

    async def test_keeps_known_persona_avatar(self, db):
        pid = _char_id()
        persona_dir = PERSONAS_DIR / pid
        persona_dir.mkdir(parents=True, exist_ok=True)
        path = str(persona_dir / "avatar.webp")
        Path(path).write_bytes(b"avatar")
        await db.execute(
            "INSERT INTO personas (id, name, description, avatar_path, created_at) VALUES (?, ?, ?, ?, ?)",
            (pid, "Test", "", path, "now"),
        )
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert Path(path).exists()
        assert result["orphaned_files"] == 0

    async def test_keeps_known_block_image(self, db):
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(BLOCKS_DIR / "img.png")
        Path(path).write_bytes(b"img")
        char_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO characters (id, name, card_json, created_at) VALUES (?, ?, ?, ?)",
            (char_id, "Test", "{}", "now"),
        )
        await db.execute(
            "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, char_id, "char", path, "image/png", 0, "now"),
        )
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert Path(path).exists()
        assert result["orphaned_files"] == 0

    async def test_keeps_known_attachment(self, db):
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(ATTACHMENTS_DIR / "doc.pdf")
        Path(path).write_bytes(b"doc")
        chat_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (chat_id, "Chat", "now", "now"),
        )
        await db.execute(
            "INSERT INTO message_attachments (id, chat_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, chat_id, path, "application/pdf", "now"),
        )
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert Path(path).exists()
        assert result["orphaned_files"] == 0

    # ── Orphan files are removed ──

    async def test_removes_orphan_attachment(self, db):
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        known = ATTACHMENTS_DIR / "known.txt"
        known.write_text("keep")
        orphan = ATTACHMENTS_DIR / "orphan.txt"
        orphan.write_text("delete")
        chat_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (chat_id, "Chat", "now", "now"),
        )
        await db.execute(
            "INSERT INTO message_attachments (id, chat_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, chat_id, str(known), "text/plain", "now"),
        )
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert known.exists()
        assert not orphan.exists()
        assert result["orphaned_files"] == 1

    async def test_removes_orphan_block_file(self, db):
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        known = BLOCKS_DIR / "known.png"
        known.write_bytes(b"img")
        orphan = BLOCKS_DIR / "orphan.png"
        orphan.write_bytes(b"img")
        char_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO characters (id, name, card_json, created_at) VALUES (?, ?, ?, ?)",
            (char_id, "Test", "{}", "now"),
        )
        await db.execute(
            "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, char_id, "char", str(known), "image/png", 0, "now"),
        )
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert known.exists()
        assert not orphan.exists()
        assert result["orphaned_files"] == 1

    async def test_removes_orphan_in_character_subdir(self, db):
        char_dir = _uuid_dir(CHARACTERS_DIR)
        blocks_dir = char_dir / "blocks"
        blocks_dir.mkdir(parents=True, exist_ok=True)
        avatar = char_dir / "avatar.png"
        avatar.write_bytes(b"avatar")
        orphan = blocks_dir / "stale.webp"
        orphan.write_bytes(b"stale")
        await db.execute(
            "INSERT INTO characters (id, name, image_path, card_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (char_dir.name, "Test", str(avatar), "{}", "now"),
        )
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert avatar.exists()
        assert not orphan.exists()
        assert result["orphaned_files"] == 1

    # ── Compressed cache ──

    async def test_purges_compressed_cache(self, db):
        COMPRESSED_DIR.mkdir(parents=True, exist_ok=True)
        (COMPRESSED_DIR / "a.webp").write_bytes(b"a")
        (COMPRESSED_DIR / "b.webp").write_bytes(b"b")
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert result["compressed_purged"] == 2
        assert not COMPRESSED_DIR.exists()

    # ── Orphaned entity directories ──

    async def test_removes_orphaned_character_directory(self, db):
        d = _uuid_dir(CHARACTERS_DIR)
        (d / "avatar.png").write_bytes(b"img")
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert not d.exists()
        assert result["orphaned_entity_dirs"] == 1

    async def test_removes_orphaned_persona_directory(self, db):
        d = _uuid_dir(PERSONAS_DIR)
        (d / "avatar.webp").write_bytes(b"img")
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert not d.exists()
        assert result["orphaned_entity_dirs"] == 1

    async def test_removes_orphaned_preset_directory(self, db):
        d = _uuid_dir(PRESETS_DIR)
        blk = d / "blocks"
        blk.mkdir()
        (blk / "img.webp").write_bytes(b"img")
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert not d.exists()
        assert result["orphaned_entity_dirs"] == 1

    async def test_preserves_valid_entity_directory(self, db):
        cid = _char_id()
        char_dir = CHARACTERS_DIR / cid
        char_dir.mkdir(parents=True, exist_ok=True)
        avatar = char_dir / "avatar.png"
        avatar.write_bytes(b"img")
        await db.execute(
            "INSERT INTO characters (id, name, image_path, card_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (cid, "Test", str(avatar), "{}", "now"),
        )
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert char_dir.exists()
        assert result["orphaned_entity_dirs"] == 0

    # ── Edge cases ──

    async def test_non_uuid_directory_not_flagged_as_entity(self, db):
        d = CHARACTERS_DIR / "config"
        d.mkdir(parents=True, exist_ok=True)
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert result["orphaned_entity_dirs"] == 0
        assert result["empty_dirs_removed"] >= 1

    async def test_empty_db_cleans_all_files(self, db):
        CHAR_DIR = _uuid_dir(CHARACTERS_DIR)
        (CHAR_DIR / "avatar.png").write_bytes(b"img")
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        (BLOCKS_DIR / "orphan.png").write_bytes(b"img")
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        (ATTACHMENTS_DIR / "orphan.pdf").write_bytes(b"doc")
        COMPRESSED_DIR.mkdir(parents=True, exist_ok=True)
        (COMPRESSED_DIR / "cache.webp").write_bytes(b"cache")
        PRESETS_DIR.mkdir(parents=True, exist_ok=True)
        _uuid_dir(PRESETS_DIR) / "blocks"
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert result["compressed_purged"] >= 1
        assert result["orphaned_entity_dirs"] >= 1
        assert result["orphaned_files"] >= 2

    async def test_no_files_no_changes(self, db):
        await db.execute(
            "INSERT INTO characters (id, name, card_json, created_at) VALUES (?, ?, ?, ?)",
            (uuid.uuid4().hex, "Test", "{}", "now"),
        )
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert result["compressed_purged"] == 0
        assert result["orphaned_entity_dirs"] == 0
        assert result["orphaned_files"] == 0
        assert result["empty_dirs_removed"] == 0

    async def test_counts_have_expected_keys(self, db):
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert set(result.keys()) == {
            "compressed_purged",
            "orphaned_entity_dirs",
            "orphaned_files",
            "empty_dirs_removed",
        }

    async def test_mixed_known_and_orphan(self, db):
        char_dir = _uuid_dir(CHARACTERS_DIR)
        avatar = char_dir / "avatar.png"
        avatar.write_bytes(b"img")
        await db.execute(
            "INSERT INTO characters (id, name, image_path, card_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (char_dir.name, "Test", str(avatar), "{}", "now"),
        )
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        known_att = ATTACHMENTS_DIR / "known.txt"
        known_att.write_text("keep")
        orphan_att = ATTACHMENTS_DIR / "orphan.txt"
        orphan_att.write_text("delete")
        chat_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (chat_id, "Chat", "now", "now"),
        )
        await db.execute(
            "INSERT INTO message_attachments (id, chat_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, chat_id, str(known_att), "text/plain", "now"),
        )
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        known_block = BLOCKS_DIR / "known.png"
        known_block.write_bytes(b"img")
        orphan_block = BLOCKS_DIR / "orphan.png"
        orphan_block.write_bytes(b"img")
        persona_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO personas (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (persona_id, "Test", "", "now"),
        )
        await db.execute(
            "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, persona_id, "persona", str(known_block), "image/png", 0, "now"),
        )
        COMPRESSED_DIR.mkdir(parents=True, exist_ok=True)
        (COMPRESSED_DIR / "cache.webp").write_bytes(b"cache")
        orphan_persona = _uuid_dir(PERSONAS_DIR)
        (orphan_persona / "avatar.webp").write_bytes(b"img")
        await db.commit()
        result = await clean_orphaned_assets(db)
        assert avatar.exists()
        assert known_att.exists()
        assert known_block.exists()
        assert not orphan_att.exists()
        assert not orphan_block.exists()
        assert not (PERSONAS_DIR / orphan_persona.name).exists()
        assert not COMPRESSED_DIR.exists() or not any(COMPRESSED_DIR.iterdir())
        assert result["compressed_purged"] == 1
        assert result["orphaned_entity_dirs"] == 1
        assert result["orphaned_files"] == 2


class TestCleanDatabase:
    # ── Soft-deleted entities are hard-deleted ──

    async def test_deletes_soft_deleted_characters(self, db):
        cid = _char_id()
        await db.execute(
            "INSERT INTO characters (id, name, card_json, created_at, is_deleted) VALUES (?, ?, ?, ?, ?)",
            (cid, "Test", "{}", "now", 1),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["characters"] == 1
        async with db.execute("SELECT 1 FROM characters WHERE id = ?", (cid,)) as cur:
            assert not await cur.fetchone()

    async def test_deletes_soft_deleted_personas(self, db):
        pid = _char_id()
        await db.execute(
            "INSERT INTO personas (id, name, description, created_at, is_deleted) VALUES (?, ?, ?, ?, ?)",
            (pid, "Test", "", "now", 1),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["personas"] == 1
        async with db.execute("SELECT 1 FROM personas WHERE id = ?", (pid,)) as cur:
            assert not await cur.fetchone()

    async def test_deletes_chats_of_deleted_character(self, db):
        cid = _char_id()
        await db.execute(
            "INSERT INTO characters (id, name, card_json, created_at, is_deleted) VALUES (?, ?, ?, ?, ?)",
            (cid, "Test", "{}", "now", 1),
        )
        chat_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO chats (id, title, character_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, "Chat", cid, "now", "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["characters"] == 1
        assert result["chats"] == 1
        async with db.execute("SELECT 1 FROM chats WHERE id = ?", (chat_id,)) as cur:
            assert not await cur.fetchone()

    async def test_preserves_active_entities(self, db):
        cid = _char_id()
        pid = _char_id()
        await db.execute(
            "INSERT INTO characters (id, name, card_json, created_at) VALUES (?, ?, ?, ?)",
            (cid, "Test", "{}", "now"),
        )
        await db.execute(
            "INSERT INTO personas (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (pid, "Test", "", "now"),
        )
        chat_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO chats (id, title, character_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (chat_id, "Chat", cid, "now", "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["chats"] == 0
        assert result["characters"] == 0
        assert result["personas"] == 0

    # ── Block images ──

    async def test_deletes_orphaned_block_images(self, db):
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(BLOCKS_DIR / "img.png")
        Path(path).write_bytes(b"img")
        await db.execute(
            "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, "nonexistent", "preset", path, "image/png", 0, "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["block_images"] == 1

    async def test_preserves_block_images_via_preset_block(self, db):
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(BLOCKS_DIR / "img.png")
        Path(path).write_bytes(b"img")
        pr_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO presets (id, name, created_at) VALUES (?, ?, ?)",
            (pr_id, "Test", "now"),
        )
        pb_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO preset_blocks (id, preset_id, name, content, role, position) VALUES (?, ?, ?, ?, ?, ?)",
            (pb_id, pr_id, "Block", "content", "system", 0),
        )
        await db.execute(
            "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, pb_id, "preset", path, "image/png", 0, "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["block_images"] == 0

    async def test_preserves_block_images_via_char_block(self, db):
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(BLOCKS_DIR / "img.png")
        Path(path).write_bytes(b"img")
        cid = _char_id()
        await db.execute(
            "INSERT INTO characters (id, name, card_json, created_at) VALUES (?, ?, ?, ?)",
            (cid, "Test", "{}", "now"),
        )
        cb_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO char_blocks (id, character_id, name, content, role, position) VALUES (?, ?, ?, ?, ?, ?)",
            (cb_id, cid, "Block", "content", "system", 0),
        )
        await db.execute(
            "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, cb_id, "char", path, "image/png", 0, "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["block_images"] == 0

    async def test_preserves_block_images_via_character_direct(self, db):
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(BLOCKS_DIR / "img.png")
        Path(path).write_bytes(b"img")
        cid = _char_id()
        await db.execute(
            "INSERT INTO characters (id, name, card_json, created_at) VALUES (?, ?, ?, ?)",
            (cid, "Test", "{}", "now"),
        )
        await db.execute(
            "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, cid, "char", path, "image/png", 0, "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["block_images"] == 0

    async def test_preserves_block_images_via_persona_direct(self, db):
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(BLOCKS_DIR / "img.png")
        Path(path).write_bytes(b"img")
        pid = _char_id()
        await db.execute(
            "INSERT INTO personas (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (pid, "Test", "", "now"),
        )
        await db.execute(
            "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, pid, "char", path, "image/png", 0, "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["block_images"] == 0

    # ── Unknown block_source fallback ──

    async def test_unknown_block_source_kept_when_valid(self, db):
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(BLOCKS_DIR / "img.png")
        Path(path).write_bytes(b"img")
        pid = _char_id()
        await db.execute(
            "INSERT INTO personas (id, name, description, created_at) VALUES (?, ?, ?, ?)",
            (pid, "Test", "", "now"),
        )
        await db.execute(
            "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, pid, "persona", path, "image/png", 0, "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["block_images"] == 0

    async def test_unknown_block_source_deleted_when_invalid(self, db):
        BLOCKS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(BLOCKS_DIR / "img.png")
        Path(path).write_bytes(b"img")
        await db.execute(
            "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, "nonexistent", "persona", path, "image/png", 0, "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["block_images"] == 1

    # ── Attachments ──

    async def test_deletes_orphaned_attachments(self, db):
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(ATTACHMENTS_DIR / "doc.pdf")
        Path(path).write_bytes(b"doc")
        chat_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (chat_id, "Chat", "now", "now"),
        )
        await db.execute(
            "INSERT INTO message_attachments (id, chat_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, chat_id, path, "application/pdf", "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["attachments"] == 1

    async def test_preserves_attachments_with_message_id(self, db):
        ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
        path = str(ATTACHMENTS_DIR / "doc.pdf")
        Path(path).write_bytes(b"doc")
        chat_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (chat_id, "Chat", "now", "now"),
        )
        msg_id = uuid.uuid4().hex
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, created_at) VALUES (?, ?, ?, ?, ?)",
            (msg_id, chat_id, "user", 0, "now"),
        )
        await db.execute(
            "INSERT INTO message_attachments (id, chat_id, message_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, chat_id, msg_id, path, "application/pdf", "now"),
        )
        await db.commit()
        result = await clean_database(db)
        assert result["attachments"] == 0

    # ── Counts ──

    async def test_counts_have_expected_keys(self, db):
        result = await clean_database(db)
        assert set(result.keys()) == {
            "chats", "characters", "personas", "block_images", "attachments",
            "compressed_purged", "orphaned_entity_dirs", "orphaned_files", "empty_dirs_removed",
        }

    async def test_empty_database_returns_zero_counts(self, db):
        result = await clean_database(db)
        for v in result.values():
            assert v == 0
