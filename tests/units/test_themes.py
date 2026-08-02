import aiosqlite
import pytest

import focus.db.themes as db_themes
from focus.core.database import SCHEMA

COLORS = {
    "--bg": "#0b0d10",
    "--surface": "#13151a",
    "--accent": "#6366f1",
    "--text": "#f1f3f5",
}


@pytest.fixture
async def db(tmp_path):
    conn = await aiosqlite.connect(tmp_path / "test.db")
    conn.row_factory = aiosqlite.Row
    await conn.executescript(SCHEMA)
    yield conn
    await conn.close()


async def test_seed_builtin_themes_idempotent(db):
    await db_themes.seed_builtin_themes(db)
    await db_themes.seed_builtin_themes(db)
    themes = await db_themes.list_themes(db)
    assert len(themes) == 3
    ids = {t["id"] for t in themes}
    assert ids == {
        db_themes.BUILTIN_SLATE_ID,
        db_themes.BUILTIN_MIDNIGHT_ID,
        db_themes.BUILTIN_LIGHT_ID,
    }
    assert all(t["is_system"] for t in themes)


async def test_create_and_get_custom_theme(db):
    theme_id = await db_themes.create_theme(db, "My Theme", COLORS)
    theme = await db_themes.get_theme(db, theme_id)
    assert theme["name"] == "My Theme"
    assert theme["colors"] == COLORS
    assert theme["is_system"] is False


async def test_update_theme_fields(db):
    theme_id = await db_themes.create_theme(db, "Old", COLORS)
    await db_themes.update_theme(db, theme_id, name="New Name")
    theme = await db_themes.get_theme(db, theme_id)
    assert theme["name"] == "New Name"
    assert theme["colors"] == COLORS
    new_colors = dict(COLORS, **{"--accent": "#123456"})
    await db_themes.update_theme(db, theme_id, colors=new_colors)
    theme = await db_themes.get_theme(db, theme_id)
    assert theme["colors"] == new_colors
    assert theme["name"] == "New Name"


async def test_reset_theme_restores_builtin(db):
    await db_themes.seed_builtin_themes(db)
    await db_themes.update_theme(
        db, db_themes.BUILTIN_SLATE_ID, name="Ruined", colors={"--bg": "#ff0000"}
    )
    ok = await db_themes.reset_theme(db, db_themes.BUILTIN_SLATE_ID)
    assert ok is True
    slate = await db_themes.get_theme(db, db_themes.BUILTIN_SLATE_ID)
    canonical = next(t for t in db_themes.BUILTIN_THEMES if t["id"] == db_themes.BUILTIN_SLATE_ID)
    assert slate["name"] == canonical["name"]
    assert slate["colors"] == canonical["colors"]


async def test_reset_theme_custom_returns_false(db):
    theme_id = await db_themes.create_theme(db, "Custom", COLORS)
    ok = await db_themes.reset_theme(db, theme_id)
    assert ok is False


async def test_delete_theme_clears_character_reference(db):
    await db_themes.seed_builtin_themes(db)
    await db.execute(
        "INSERT INTO characters (id, name, card_json, created_at, theme_id) VALUES (?, ?, ?, ?, ?)",
        ("char-1", "C", "{}", "2026-01-01T00:00:00+00:00", db_themes.BUILTIN_SLATE_ID),
    )
    await db_themes.delete_theme(db, db_themes.BUILTIN_SLATE_ID)
    async with db.execute("SELECT theme_id FROM characters WHERE id = 'char-1'") as cur:
        row = await cur.fetchone()
    assert row["theme_id"] is None


async def test_delete_legacy_theme_setting(db):
    await db.execute("INSERT INTO settings (key, value) VALUES ('theme_json', '{}')")
    await db.execute("INSERT INTO settings (key, value) VALUES ('active_theme_id', 'builtin-slate')")
    await db.execute("INSERT INTO settings (key, value) VALUES ('theme_mode', 'auto')")
    await db.execute("INSERT INTO settings (key, value) VALUES ('other', '1')")
    await db_themes.delete_legacy_theme_setting(db)
    async with db.execute("SELECT key FROM settings") as cur:
        keys = [r["key"] for r in await cur.fetchall()]
    assert "theme_json" not in keys
    assert "active_theme_id" not in keys
    assert "theme_mode" not in keys
    assert "other" in keys


async def test_theme_state_defaults(db):
    await db_themes.seed_builtin_themes(db)
    state = await db_themes.get_theme_state(db)
    assert state["dark_theme_id"] == db_themes.BUILTIN_SLATE_ID
    assert state["light_theme_id"] == db_themes.BUILTIN_LIGHT_ID


async def test_theme_state_custom_slots(db):
    await db_themes.seed_builtin_themes(db)
    theme_id = await db_themes.create_theme(db, "T", COLORS)
    await db_themes.set_setting(db, db_themes.DARK_SLOT_KEY, theme_id)
    await db_themes.set_setting(db, db_themes.LIGHT_SLOT_KEY, db_themes.BUILTIN_MIDNIGHT_ID)
    state = await db_themes.get_theme_state(db)
    assert state["dark_theme_id"] == theme_id
    assert state["light_theme_id"] == db_themes.BUILTIN_MIDNIGHT_ID


async def test_theme_state_dangling_slot_falls_back(db):
    await db_themes.seed_builtin_themes(db)
    await db_themes.set_setting(db, db_themes.DARK_SLOT_KEY, "theme-missing")
    await db_themes.set_setting(db, db_themes.LIGHT_SLOT_KEY, "theme-missing")
    state = await db_themes.get_theme_state(db)
    assert state["dark_theme_id"] == db_themes.BUILTIN_SLATE_ID
    assert state["light_theme_id"] == db_themes.BUILTIN_LIGHT_ID
