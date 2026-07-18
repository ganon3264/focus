import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from pyvern.database import get_db
from pyvern.card_parser import extract_card_json, normalise_card
from pyvern.models import CharBlockCreate, CharBlockUpdate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Import ────────────────────────────────────────────────────────────────────

@router.post("/import", status_code=201)
async def import_character(
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    data = await file.read()

    try:
        raw_json = extract_card_json(data)
    except ValueError as e:
        raise HTTPException(400, str(e))

    card = normalise_card(raw_json)
    char_id = str(uuid.uuid4())
    now = _now()

    # Persist avatar image
    avatar_path = f"avatars/{char_id}.png"
    Path(avatar_path).write_bytes(data)

    await db.execute(
        "INSERT INTO characters (id, name, image_path, card_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (char_id, card["name"], avatar_path, json.dumps(raw_json), now),
    )
    await db.commit()

    return {"id": char_id, "name": card["name"]}


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("/")
async def list_characters(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT id, name, image_path, created_at FROM characters ORDER BY name"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/{char_id}")
async def get_character(char_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM characters WHERE id = ?", (char_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Character not found")

    async with db.execute(
        "SELECT * FROM char_blocks WHERE character_id = ? ORDER BY position", (char_id,)
    ) as cur:
        blocks = [dict(r) for r in await cur.fetchall()]

    result = dict(row)
    result["card"] = normalise_card(json.loads(result.pop("card_json")))
    result["blocks"] = blocks
    return result


@router.delete("/{char_id}", status_code=204)
async def delete_character(char_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT image_path FROM characters WHERE id = ?", (char_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Character not found")

    if row["image_path"]:
        Path(row["image_path"]).unlink(missing_ok=True)

    await db.execute("DELETE FROM characters WHERE id = ?", (char_id,))
    await db.commit()


# ── Character-exclusive blocks ────────────────────────────────────────────────

@router.get("/{char_id}/blocks")
async def list_char_blocks(char_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT * FROM char_blocks WHERE character_id = ? ORDER BY position", (char_id,)
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.post("/{char_id}/blocks", status_code=201)
async def create_char_block(
    char_id: str,
    body: CharBlockCreate,
    db: aiosqlite.Connection = Depends(get_db),
):
    block_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO char_blocks (id, character_id, name, content, role, enabled, position) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (block_id, char_id, body.name, body.content, body.role, int(body.enabled), body.position),
    )
    await db.commit()
    return {"id": block_id}


@router.patch("/{char_id}/blocks/{block_id}")
async def update_char_block(
    char_id: str,
    block_id: str,
    body: CharBlockUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"ok": True}
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [block_id, char_id]
    await db.execute(
        f"UPDATE char_blocks SET {cols} WHERE id = ? AND character_id = ?", vals
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{char_id}/blocks/{block_id}", status_code=204)
async def delete_char_block(
    char_id: str,
    block_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    await db.execute(
        "DELETE FROM char_blocks WHERE id = ? AND character_id = ?", (block_id, char_id)
    )
    await db.commit()
