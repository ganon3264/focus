from __future__ import annotations

import json

import aiosqlite


async def get_config(db: aiosqlite.Connection, name: str) -> dict:
    async with db.execute("SELECT config_json FROM extension_configs WHERE name = ?", (name,)) as cur:
        row = await cur.fetchone()
    if not row or not row["config_json"]:
        return {}
    try:
        return json.loads(row["config_json"])
    except (TypeError, ValueError):
        return {}


async def set_config(db: aiosqlite.Connection, name: str, config: dict) -> None:
    await db.execute(
        "INSERT INTO extension_configs (name, config_json) VALUES (?, ?) "
        "ON CONFLICT(name) DO UPDATE SET config_json = excluded.config_json",
        (name, json.dumps(config)),
    )


async def get_configs(db: aiosqlite.Connection) -> dict[str, dict]:
    async with db.execute("SELECT name, config_json FROM extension_configs") as cur:
        rows = await cur.fetchall()
    out: dict[str, dict] = {}
    for row in rows:
        try:
            out[row["name"]] = json.loads(row["config_json"])
        except (TypeError, ValueError):
            out[row["name"]] = {}
    return out


async def get_chat_states(db: aiosqlite.Connection, chat_id: str) -> dict[str, bool]:
    async with db.execute(
        "SELECT name, enabled FROM extension_states WHERE chat_id = ?", (chat_id,)
    ) as cur:
        rows = await cur.fetchall()
    return {row["name"]: bool(row["enabled"]) for row in rows}


async def set_chat_states(db: aiosqlite.Connection, chat_id: str, states: dict[str, bool]) -> None:
    for name, enabled in states.items():
        await db.execute(
            "INSERT INTO extension_states (chat_id, name, enabled) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id, name) DO UPDATE SET enabled = excluded.enabled",
            (chat_id, name, enabled),
        )


async def get_enabled_extensions(db: aiosqlite.Connection, chat_id: str) -> list:
    """Return the ExtensionSpec objects enabled for *chat_id* (for toolbar rendering)."""
    from focus.extensions.loader import get_all_extensions

    states = await get_chat_states(db, chat_id)
    return [spec for spec in get_all_extensions() if states.get(spec.name, False)]
