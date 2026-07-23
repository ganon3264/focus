from __future__ import annotations

import json
import uuid
from pathlib import Path

import aiosqlite

from focus.core.card_parser import normalise_card, parse_card_bytes, validate_card_warnings
from focus.core.paths import CHARACTERS_DIR
from focus.core.utils import now_iso


async def import_character(
    db: aiosqlite.Connection, file_data: bytes, filename: str
) -> dict:
    raw_json = parse_card_bytes(file_data)
    warnings = validate_card_warnings(raw_json)
    card = normalise_card(raw_json)
    char_id = str(uuid.uuid4())
    now = now_iso()
    char_dir = CHARACTERS_DIR / char_id
    char_dir.mkdir(parents=True, exist_ok=True)
    avatar_path = str(char_dir / "avatar.png")
    Path(avatar_path).write_bytes(file_data)

    await db.execute(
        "INSERT INTO characters (id, name, image_path, card_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (char_id, card["name"], avatar_path, json.dumps(raw_json), now),
    )

    entry: dict = {"id": char_id, "name": card["name"]}
    if warnings:
        entry["warnings"] = warnings
    return entry


async def create_character(
    db: aiosqlite.Connection,
    name: str,
    description: str = "",
    personality: str = "",
    scenario: str = "",
    mes_example: str = "",
    first_mes: str = "",
    alternate_greetings: list[str] | None = None,
) -> str:
    char_id = str(uuid.uuid4())
    now = now_iso()
    card_json = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": name,
            "description": description,
            "personality": personality,
            "scenario": scenario,
            "mes_example": mes_example,
            "first_mes": first_mes,
            "alternate_greetings": alternate_greetings or [],
        },
    }
    await db.execute(
        "INSERT INTO characters (id, name, image_path, card_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (char_id, name, None, json.dumps(card_json), now),
    )
    return char_id


async def update_character(db: aiosqlite.Connection, char_id: str, updates: dict) -> None:
    async with db.execute("SELECT card_json FROM characters WHERE id = ?", (char_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Character not found")
    try:
        card = json.loads(row["card_json"])
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raise HTTPException(500, "Character card data is corrupt")

    data = card.get("data", card)
    data.update(updates)
    card["data"] = data

    extra = {}
    if "name" in updates:
        extra["name"] = updates["name"]

    set_clause = "card_json = ?"
    vals = [json.dumps(card)]
    for k, v in extra.items():
        set_clause += f", {k} = ?"
        vals.append(v)
    vals.append(char_id)
    await db.execute(f"UPDATE characters SET {set_clause} WHERE id = ?", vals)


async def update_character_avatar(db: aiosqlite.Connection, char_id: str, avatar_path: str) -> None:
    await db.execute("UPDATE characters SET image_path = ? WHERE id = ?", (avatar_path, char_id))


async def delete_character(db: aiosqlite.Connection, char_id: str, delete_chats: bool = False) -> Path | None:
    await db.execute("UPDATE characters SET is_deleted = 1 WHERE id = ?", (char_id,))
    if delete_chats:
        await db.execute("UPDATE chats SET is_deleted = 1 WHERE character_id = ?", (char_id,))
    async with db.execute("SELECT image_path FROM characters WHERE id = ?", (char_id,)) as cur:
        row = await cur.fetchone()
    return row["image_path"] if row else None


async def hard_delete_character(db: aiosqlite.Connection, char_id: str) -> str | None:
    async with db.execute("SELECT image_path FROM characters WHERE id = ?", (char_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Character not found")
    await db.execute("DELETE FROM characters WHERE id = ?", (char_id,))
    return row["image_path"]


async def restore_character(db: aiosqlite.Connection, char_id: str, restore_chats: bool = False) -> None:
    await db.execute("UPDATE characters SET is_deleted = 0 WHERE id = ?", (char_id,))
    if restore_chats:
        await db.execute("UPDATE chats SET is_deleted = 0 WHERE character_id = ?", (char_id,))


async def create_char_block(
    db: aiosqlite.Connection,
    character_id: str,
    name: str,
    content: str = "",
    role: str = "system",
    enabled: bool = True,
    position: float = 0.0,
) -> str:
    block_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO char_blocks (id, character_id, name, content, role, enabled, position) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (block_id, character_id, name, content, role, int(enabled), position),
    )
    return block_id


async def update_char_block(
    db: aiosqlite.Connection, character_id: str, block_id: str, updates: dict
) -> None:
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [block_id, character_id]
    await db.execute(f"UPDATE char_blocks SET {cols} WHERE id = ? AND character_id = ?", vals)


async def delete_char_block(db: aiosqlite.Connection, character_id: str, block_id: str) -> None:
    await db.execute("DELETE FROM char_blocks WHERE id = ? AND character_id = ?", (block_id, character_id))
