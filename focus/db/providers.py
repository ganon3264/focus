from __future__ import annotations

import json
import uuid

import aiosqlite

from focus.core.utils import now_iso


async def create_provider(
    db: aiosqlite.Connection,
    name: str,
    type: str,
    base_url: str | None,
    api_key: str | None,
    model: str,
    params: dict | None = None,
) -> str:
    provider_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO providers (id, name, type, base_url, api_key, model, params_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (provider_id, name, type, base_url, api_key, model, json.dumps(params or {}), now_iso()),
    )
    return provider_id


async def update_provider(db: aiosqlite.Connection, provider_id: str, updates: dict) -> None:
    allowed = {"name", "base_url", "api_key", "model", "params_json"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    if "api_key" in updates and not updates["api_key"]:
        del updates["api_key"]
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [provider_id]
    await db.execute(f"UPDATE providers SET {cols} WHERE id = ?", vals)


async def delete_provider(db: aiosqlite.Connection, provider_id: str) -> None:
    await db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))


async def upsert_secret(db: aiosqlite.Connection, name: str, value: str) -> None:
    if not value:
        await db.execute("DELETE FROM secrets WHERE name = ?", (name,))
    else:
        await db.execute(
            "INSERT INTO secrets (name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (name, value),
        )


async def delete_secret(db: aiosqlite.Connection, name: str) -> None:
    await db.execute("DELETE FROM secrets WHERE name = ?", (name,))
