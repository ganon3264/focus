import aiosqlite
import pytest

import focus.core.database as database


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
        assert count == 3, "built-in themes seeded"

        async with db.execute("SELECT COUNT(*) AS c FROM themes WHERE is_system = 1") as cur:
            system = (await cur.fetchone())["c"]
        assert system == 3, "all built-ins flagged system"

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
            assert (await cur.fetchone())["c"] == 3
