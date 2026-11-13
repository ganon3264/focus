import aiosqlite
import pytest

import focus.core.database as database
from focus.db.themes import BUILTIN_THEMES

LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS characters (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    image_path  TEXT,
    card_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    is_deleted  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS personas (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    avatar_path TEXT,
    created_at  TEXT NOT NULL,
    is_deleted  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# regex_scripts as created by 8cd5f0f, before destination became
# apply_prompt/apply_display/as_block.
OLD_REGEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS regex_scripts (
    id          TEXT PRIMARY KEY,
    scope       TEXT NOT NULL DEFAULT 'global',
    scope_id    TEXT,
    name        TEXT NOT NULL DEFAULT '',
    pattern     TEXT NOT NULL,
    replacement TEXT NOT NULL DEFAULT '',
    flags       TEXT NOT NULL DEFAULT '',
    placement   TEXT NOT NULL DEFAULT 'ai',
    destination TEXT NOT NULL DEFAULT 'ephemeral',
    enabled     INTEGER NOT NULL DEFAULT 1,
    position    REAL NOT NULL DEFAULT 0,
    min_depth   INTEGER NOT NULL DEFAULT 0,
    max_depth   INTEGER NOT NULL DEFAULT -1,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
INSERT INTO regex_scripts (id, pattern, destination, created_at, updated_at)
VALUES ('eph', 'a', 'ephemeral', 'x', 'x'), ('cos', 'b', 'cosmetic', 'x', 'x');
"""


@pytest.fixture
async def legacy_db(tmp_path, monkeypatch):
    """A pre-themes database plus a redirected DB path for init_db()."""
    db_path = tmp_path / "focus.db"
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(LEGACY_SCHEMA)
        await db.execute("INSERT INTO settings (key, value) VALUES ('theme_json', '{\"--accent\":\"#ff0000\"}')")
        await db.commit()

    monkeypatch.setattr(database, "DB_PATH", db_path)
    yield db_path


async def test_init_db_migrates_legacy_database(legacy_db, monkeypatch):
    await database.init_db()

    async with aiosqlite.connect(str(legacy_db)) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute("SELECT COUNT(*) AS c FROM themes") as cur:
            count = (await cur.fetchone())["c"]
        assert count == len(BUILTIN_THEMES), "built-in themes seeded"

        async with db.execute("SELECT COUNT(*) AS c FROM themes WHERE is_system = 1") as cur:
            system = (await cur.fetchone())["c"]
        assert system == len(BUILTIN_THEMES), "all built-ins flagged system"

        cols = await db.execute("PRAGMA table_info(characters)")
        col_names = {row[1] for row in await cols.fetchall()}
        assert "theme_id" in col_names, "characters.theme_id added"

        async with db.execute("SELECT COUNT(*) AS c FROM settings WHERE key = 'theme_json'") as cur:
            legacy = (await cur.fetchone())["c"]
        assert legacy == 0, "legacy theme_json setting dropped"

        # Default persona seeded by init_db
        async with db.execute("SELECT COUNT(*) AS c FROM personas") as cur:
            assert (await cur.fetchone())["c"] == 1


async def test_init_db_idempotent_on_legacy_database(legacy_db, monkeypatch):
    await database.init_db()
    await database.init_db()

    async with aiosqlite.connect(str(legacy_db)) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT COUNT(*) AS c FROM themes") as cur:
            assert (await cur.fetchone())["c"] == len(BUILTIN_THEMES)


@pytest.fixture
async def regex_legacy_db(tmp_path, monkeypatch):
    """A database carrying the pre-structured regex_scripts schema."""
    db_path = tmp_path / "focus.db"
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(LEGACY_SCHEMA + OLD_REGEX_SCHEMA)
        await db.commit()

    monkeypatch.setattr(database, "DB_PATH", db_path)
    yield db_path


async def test_init_db_migrates_regex_destination(regex_legacy_db):
    await database.init_db()

    async with aiosqlite.connect(str(regex_legacy_db)) as db:
        db.row_factory = aiosqlite.Row
        cols = await db.execute("PRAGMA table_info(regex_scripts)")
        col_names = {row[1] for row in await cols.fetchall()}
        assert "destination" not in col_names
        assert {"apply_prompt", "apply_display", "as_block"} <= col_names

        async with db.execute("SELECT * FROM regex_scripts") as cur:
            rows = {r["id"]: r for r in await cur.fetchall()}
        assert rows["eph"]["apply_prompt"] == 1
        assert rows["eph"]["apply_display"] == 1
        assert rows["cos"]["apply_prompt"] == 0
        assert rows["cos"]["apply_display"] == 1
        assert all(r["as_block"] == 0 for r in rows.values())

    # Second boot must not re-run the migration.
    await database.init_db()


@pytest.fixture
async def legacy_variants_db(tmp_path, monkeypatch):
    """A database whose variants still carry the pre-variant_meta columns."""
    db_path = tmp_path / "focus.db"
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(database.SCHEMA)
        await db.execute("ALTER TABLE message_variants ADD COLUMN reasoning TEXT")
        await db.execute("ALTER TABLE message_variants ADD COLUMN reasoning_details TEXT")
        await db.execute("ALTER TABLE message_variants DROP COLUMN variant_meta")
        await db.execute("PRAGMA foreign_keys=OFF")
        await db.execute(
            "INSERT INTO message_variants"
            " (id, message_id, variant_index, content, created_at, reasoning, reasoning_details)"
            " VALUES ('v1', 'm1', 0, 'hi', 'x', 'thinking', '[{\"id\": \"d1\"}]')"
        )
        await db.commit()

    monkeypatch.setattr(database, "DB_PATH", db_path)
    yield db_path


async def test_init_db_folds_legacy_reasoning_into_variant_meta(legacy_variants_db):
    import json

    await database.init_db()

    async with aiosqlite.connect(str(legacy_variants_db)) as db:
        db.row_factory = aiosqlite.Row
        cols = await db.execute("PRAGMA table_info(message_variants)")
        col_names = {row[1] for row in await cols.fetchall()}
        assert "variant_meta" in col_names
        assert "reasoning" not in col_names
        assert "reasoning_details" not in col_names

        async with db.execute("SELECT variant_meta FROM message_variants WHERE id = 'v1'") as cur:
            meta = json.loads((await cur.fetchone())["variant_meta"])
        assert meta["reasoning"] == "thinking"
        assert meta["reasoning_details"] == [{"id": "d1"}]


async def test_second_boot_rewrites_no_table(tmp_path, monkeypatch):
    """A current database must boot without DDL — retiring a column rewrites
    the whole table, and that must not happen on every start."""
    db_path = tmp_path / "focus.db"
    async with aiosqlite.connect(db_path) as db:
        await db.executescript(database.SCHEMA)
        await db.commit()

    monkeypatch.setattr(database, "DB_PATH", db_path)
    await database.init_db()

    async def schema_version():
        async with aiosqlite.connect(str(db_path)) as db:
            async with db.execute("PRAGMA schema_version") as cur:
                return (await cur.fetchone())[0]

    before = await schema_version()
    await database.init_db()
    assert await schema_version() == before
