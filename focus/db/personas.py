from __future__ import annotations

import uuid
from pathlib import Path

import aiosqlite

from focus.core.utils import now_iso


async def create_persona(db: aiosqlite.Connection, name: str, description: str = "") -> str:
    persona_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO personas (id, name, description, avatar_path, created_at) VALUES (?, ?, ?, ?, ?)",
        (persona_id, name, description, None, now_iso()),
    )
    return persona_id


async def update_persona(db: aiosqlite.Connection, persona_id: str, updates: dict) -> None:
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [persona_id]
    await db.execute(f"UPDATE personas SET {cols} WHERE id = ?", vals)


async def update_persona_avatar(db: aiosqlite.Connection, persona_id: str, avatar_path: str) -> None:
    await db.execute("UPDATE personas SET avatar_path = ? WHERE id = ?", (avatar_path, persona_id))


async def delete_persona(db: aiosqlite.Connection, persona_id: str) -> Path | None:
    async with db.execute("SELECT avatar_path FROM personas WHERE id = ?", (persona_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Persona not found")
    avatar_path = row["avatar_path"]
    await db.execute("UPDATE personas SET is_deleted = 1 WHERE id = ?", (persona_id,))
    return avatar_path


async def hard_delete_persona(db: aiosqlite.Connection, persona_id: str) -> Path | None:
    async with db.execute("SELECT avatar_path FROM personas WHERE id = ?", (persona_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Persona not found")
    avatar_path = row["avatar_path"]
    await db.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
    return avatar_path


async def restore_persona(db: aiosqlite.Connection, persona_id: str) -> None:
    await db.execute("UPDATE personas SET is_deleted = 0 WHERE id = ?", (persona_id,))
