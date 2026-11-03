from __future__ import annotations

import json
import uuid

import aiosqlite

from focus.core.utils import now_iso

BUILTIN_SLATE_ID = "builtin-slate"
BUILTIN_MIDNIGHT_ID = "builtin-midnight"
BUILTIN_LIGHT_ID = "builtin-light"

RETIRED_BUILTIN_IDS = ("builtin-instrument",)

BUILTIN_THEMES = [
    {
        "id": BUILTIN_SLATE_ID,
        "name": "Graphite",
        "colors": {
            "--bg": "#121213",
            "--surface": "#1c1c1e",
            "--surface-2": "#262628",
            "--surface-3": "#323234",
            "--border": "#3e3e42",
            "--accent": "#3b82f6",
            "--text": "#ececee",
            "--text-muted": "#a2a2a8",
            "--text-faint": "#74757b",
            "--role-user": "#34d399",
            "--role-assistant": "#fbbf24",
        },
    },
    {
        "id": BUILTIN_LIGHT_ID,
        "name": "Paper",
        "colors": {
            "--bg": "#f5f6f8",
            "--surface": "#ffffff",
            "--surface-2": "#eef0f3",
            "--surface-3": "#e1e4e9",
            "--border": "#d3d7de",
            "--accent": "#1d4ed8",
            "--text": "#15181d",
            "--text-muted": "#59606d",
            "--text-faint": "#7d838e",
            "--role-user": "#047857",
            "--role-assistant": "#b45309",
        },
    },
    {
        "id": BUILTIN_MIDNIGHT_ID,
        "name": "Void (OLED)",
        "colors": {
            "--bg": "#000000",
            "--surface": "#08090a",
            "--surface-2": "#101214",
            "--surface-3": "#191c1f",
            "--border": "#24282d",
            "--accent": "#a3e635",
            "--text": "#f3f4f6",
            "--text-muted": "#9aa3ad",
            "--text-faint": "#6b737d",
            "--role-user": "#22d3ee",
            "--role-assistant": "#c084fc",
        },
    },
]

# The palettes the previous built-in seeds shipped. Used only by the migration:
# a row still carrying these exact colours is untouched, so a user's in-place
# edits are never overwritten. Edited rows are left alone (Reset repaints them).
LEGACY_BUILTIN_COLORS = {
    "builtin-slate": {
        "--bg": "#1b1e23",
        "--surface": "#2a2e34",
        "--surface-2": "#32373e",
        "--surface-3": "#3c424a",
        "--border": "#444b54",
        "--accent": "#6366f1",
        "--text": "#eef0f3",
        "--text-muted": "#9aa3ae",
        "--role-user": "#10b981",
        "--role-assistant": "#f59e0b",
    },
    "builtin-midnight": {
        "--bg": "#000000",
        "--surface": "#090909",
        "--surface-2": "#111111",
        "--surface-3": "#1a1a1a",
        "--border": "#222222",
        "--accent": "#3b82f6",
        "--text": "#ffffff",
        "--text-muted": "#9ca3af",
        "--role-user": "#34d399",
        "--role-assistant": "#fbbf24",
    },
    "builtin-light": {
        "--bg": "#f8fafc",
        "--surface": "#ffffff",
        "--surface-2": "#f1f5f9",
        "--surface-3": "#e2e8f0",
        "--border": "#e2e8f0",
        "--accent": "#4f46e5",
        "--text": "#0f172a",
        "--text-muted": "#64748b",
        "--role-user": "#059669",
        "--role-assistant": "#d97706",
    },
}

DARK_SLOT_KEY = "dark_theme_id"
LIGHT_SLOT_KEY = "light_theme_id"


def _row_to_dict(row: aiosqlite.Row) -> dict:
    theme = dict(row)
    theme["colors"] = json.loads(theme.pop("colors_json") or "{}")
    theme["is_system"] = bool(theme["is_system"])
    return theme


async def seed_builtin_themes(db: aiosqlite.Connection) -> None:
    """Insert built-in themes if missing (idempotent)."""
    for theme in BUILTIN_THEMES:
        async with db.execute("SELECT id FROM themes WHERE id = ?", (theme["id"],)) as cur:
            if await cur.fetchone():
                continue
        await db.execute(
            "INSERT INTO themes (id, name, colors_json, is_system, created_at) VALUES (?, ?, ?, 1, ?)",
            (theme["id"], theme["name"], json.dumps(theme["colors"]), now_iso()),
        )


async def migrate_builtin_themes(db: aiosqlite.Connection) -> None:
    """Repaint unedited built-ins and drop retired ids. Idempotent."""
    for theme in BUILTIN_THEMES:
        legacy = LEGACY_BUILTIN_COLORS.get(theme["id"])
        if legacy is None:
            continue
        async with db.execute(
            "SELECT colors_json FROM themes WHERE id = ? AND is_system = 1", (theme["id"],)
        ) as cur:
            row = await cur.fetchone()
        if not row or json.loads(row["colors_json"] or "{}") != legacy:
            continue
        await db.execute(
            "UPDATE themes SET name = ?, colors_json = ? WHERE id = ? AND is_system = 1",
            (theme["name"], json.dumps(theme["colors"]), theme["id"]),
        )
    for retired in RETIRED_BUILTIN_IDS:
        await db.execute("UPDATE characters SET theme_id = NULL WHERE theme_id = ?", (retired,))
        await db.execute(
            "DELETE FROM settings WHERE key IN (?, ?) AND value = ?",
            (DARK_SLOT_KEY, LIGHT_SLOT_KEY, retired),
        )
        await db.execute("DELETE FROM themes WHERE id = ? AND is_system = 1", (retired,))


async def delete_legacy_theme_setting(db: aiosqlite.Connection) -> None:
    """Drop the legacy single-slot theme settings (superseded by the pair model)."""
    await db.execute("DELETE FROM settings WHERE key IN ('theme_json', 'active_theme_id', 'theme_mode')")


async def list_themes(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute(
        "SELECT id, name, colors_json, is_system, created_at FROM themes "
        "ORDER BY is_system DESC, created_at ASC"
    ) as cur:
        return [_row_to_dict(r) for r in await cur.fetchall()]


async def get_theme(db: aiosqlite.Connection, theme_id: str) -> dict | None:
    async with db.execute(
        "SELECT id, name, colors_json, is_system, created_at FROM themes WHERE id = ?",
        (theme_id,),
    ) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row) if row else None


async def create_theme(
    db: aiosqlite.Connection,
    name: str,
    colors: dict,
) -> str:
    theme_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO themes (id, name, colors_json, is_system, created_at) VALUES (?, ?, ?, 0, ?)",
        (theme_id, name, json.dumps(colors), now_iso()),
    )
    return theme_id


UNSET = object()


async def update_theme(
    db: aiosqlite.Connection,
    theme_id: str,
    name=UNSET,
    colors=UNSET,
) -> None:
    sets = []
    vals: list = []
    if name is not UNSET:
        sets.append("name = ?")
        vals.append(name)
    if colors is not UNSET:
        sets.append("colors_json = ?")
        vals.append(json.dumps(colors))
    if not sets:
        return
    vals.append(theme_id)
    await db.execute(f"UPDATE themes SET {', '.join(sets)} WHERE id = ?", vals)


async def reset_theme(db: aiosqlite.Connection, theme_id: str) -> bool:
    """Restore a built-in theme to its canonical seed values. False if not a built-in."""
    canonical = next((t for t in BUILTIN_THEMES if t["id"] == theme_id), None)
    if not canonical:
        return False
    await db.execute(
        "UPDATE themes SET name = ?, colors_json = ? WHERE id = ?",
        (canonical["name"], json.dumps(canonical["colors"]), theme_id),
    )
    return True


async def delete_theme(db: aiosqlite.Connection, theme_id: str) -> None:
    await db.execute("DELETE FROM themes WHERE id = ?", (theme_id,))
    await db.execute("UPDATE characters SET theme_id = NULL WHERE theme_id = ?", (theme_id,))


async def get_setting(db: aiosqlite.Connection, key: str, default: str | None = None) -> str | None:
    async with db.execute("SELECT value FROM settings WHERE key = ?", (key,)) as cur:
        row = await cur.fetchone()
    return row["value"] if row else default


async def set_setting(db: aiosqlite.Connection, key: str, value: str) -> None:
    await db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


async def get_theme_state(db: aiosqlite.Connection) -> dict:
    """Theme slot state with defensive fallbacks: dark → slate, light → light."""
    dark = await get_setting(db, DARK_SLOT_KEY)
    if not dark or not await get_theme(db, dark):
        dark = BUILTIN_SLATE_ID
    light = await get_setting(db, LIGHT_SLOT_KEY)
    if not light or not await get_theme(db, light):
        light = BUILTIN_LIGHT_ID
    return {"dark_theme_id": dark, "light_theme_id": light}
