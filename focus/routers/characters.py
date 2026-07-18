import json
import logging
import uuid
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

import focus.crud as crud
from focus.card_parser import extract_card_json, normalise_card
from focus.database import get_db
from focus.models import CharacterCreate, CharacterUpdate, CharBlockCreate, CharBlockUpdate
from focus.paths import BLOCKS_DIR, CHARACTERS_DIR
from focus.utils import now_iso

router = APIRouter()
logger = logging.getLogger("focus.routers.characters")

@router.post("/import", status_code=201)
async def import_character(
    files: list[UploadFile] = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    imported = []
    errors = []

    for file in files:
        data = await file.read()

        try:
            raw_json = extract_card_json(data)
        except ValueError as e:
            errors.append({"filename": file.filename, "error": str(e)})
            continue

        try:
            card = normalise_card(raw_json)
        except Exception as e:
            errors.append({"filename": file.filename, "error": f"Invalid card format: {e}"})
            continue

        char_id = str(uuid.uuid4())
        now = now_iso()

        char_dir = CHARACTERS_DIR / char_id
        char_dir.mkdir(parents=True, exist_ok=True)
        avatar_path = str(char_dir / "avatar.png")
        try:
            Path(avatar_path).write_bytes(data)
        except OSError as e:
            raise HTTPException(500, f"Failed to save avatar: {e}")

        await db.execute(
            "INSERT INTO characters (id, name, image_path, card_json, created_at) VALUES (?, ?, ?, ?, ?)",
            (char_id, card["name"], avatar_path, json.dumps(raw_json), now),
        )
        imported.append({"id": char_id, "name": card["name"]})

    await db.commit()

    result = {"imported": imported, "total": len(imported) + len(errors)}
    if errors:
        result["errors"] = errors
    return result

@router.post("/", status_code=201)
async def create_character(body: CharacterCreate, db: aiosqlite.Connection = Depends(get_db)):
    char_id = str(uuid.uuid4())
    now = now_iso()
    card_json = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": body.name,
            "description": body.description,
            "personality": body.personality,
            "scenario": body.scenario,
            "mes_example": body.mes_example,
            "first_mes": body.first_mes,
            "alternate_greetings": body.alternate_greetings,
        },
    }
    char_dir = CHARACTERS_DIR / char_id
    char_dir.mkdir(parents=True, exist_ok=True)

    await db.execute(
        "INSERT INTO characters (id, name, image_path, card_json, created_at) VALUES (?, ?, ?, ?, ?)",
        (char_id, body.name, None, json.dumps(card_json), now),
    )
    await db.commit()
    return {"id": char_id, "name": body.name}

@router.patch("/{char_id}")
async def update_character(
    char_id: str,
    body: CharacterUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("SELECT card_json FROM characters WHERE id = ?", (char_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Character not found")

    try:
        card = json.loads(row["card_json"])
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        logger.warning("Corrupted card_json for character %s: %s", char_id, e)
        raise HTTPException(500, "Character card data is corrupt")
    data = card.get("data", card)
    updates = body.model_dump(exclude_none=True)
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
    await db.commit()
    return {"ok": True}

@router.post("/{char_id}/avatar")
async def upload_avatar(
    char_id: str,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("SELECT image_path FROM characters WHERE id = ?", (char_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Character not found")

    if row["image_path"]:
        Path(row["image_path"]).unlink(missing_ok=True)

    suffix = Path(file.filename).suffix.lower() or ".png"
    char_dir = CHARACTERS_DIR / char_id
    char_dir.mkdir(parents=True, exist_ok=True)
    avatar_path = str(char_dir / f"avatar{suffix}")
    try:
        Path(avatar_path).write_bytes(await file.read())
    except OSError as e:
        raise HTTPException(500, f"Failed to save avatar: {e}")

    await db.execute("UPDATE characters SET image_path = ? WHERE id = ?", (avatar_path, char_id))
    await db.commit()
    return {"avatar_path": avatar_path}

@router.get("/")
async def list_characters(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT id, name, image_path, created_at FROM characters WHERE is_deleted = 0 ORDER BY name"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]

@router.get("/trash")
async def list_trashed_characters(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT id, name, image_path, created_at FROM characters WHERE is_deleted = 1 ORDER BY name"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]

@router.get("/{char_id}")
async def get_character(char_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM characters WHERE id = ?", (char_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Character not found")

    blocks = await crud.load_entity_blocks(db, "char_blocks", "character_id", char_id)

    result = dict(row)
    card_raw = result.pop("card_json")
    try:
        result["card"] = json.loads(card_raw) if card_raw else {}
    except (json.JSONDecodeError, TypeError):
        result["card"] = {}
    result["blocks"] = blocks
    return result

@router.delete("/{char_id}", status_code=204)
async def delete_character(
    char_id: str,
    hard: bool = False,
    delete_chats: bool = False,
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("SELECT image_path FROM characters WHERE id = ?", (char_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Character not found")

    if hard:
        if row["image_path"]:
            Path(row["image_path"]).unlink(missing_ok=True)
        await db.execute("DELETE FROM characters WHERE id = ?", (char_id,))
    else:
        await db.execute("UPDATE characters SET is_deleted = 1 WHERE id = ?", (char_id,))
        if delete_chats:
            await db.execute("UPDATE chats SET is_deleted = 1 WHERE character_id = ?", (char_id,))
    await db.commit()

@router.post("/{char_id}/restore", status_code=200)
async def restore_character(
    char_id: str, restore_chats: bool = False, db: aiosqlite.Connection = Depends(get_db)
):
    await db.execute("UPDATE characters SET is_deleted = 0 WHERE id = ?", (char_id,))
    if restore_chats:
        await db.execute("UPDATE chats SET is_deleted = 0 WHERE character_id = ?", (char_id,))
    await db.commit()
    return {"ok": True}

@router.post("/{char_id}/images", status_code=201)
async def add_char_image(
    char_id: str,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    await crud.verify_entity_exists(db, "characters", char_id)
    try:
        return await crud.upload_block_image(
            db,
            char_id,
            "char",
            await file.read(),
            file.filename,
            file.content_type,
            str(BLOCKS_DIR),
            images_only=False,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to save image: {str(e)}")

@router.delete("/{char_id}/images/{image_id}", status_code=204)
async def delete_char_image(
    char_id: str,
    image_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    await crud.delete_block_image(db, image_id, char_id)

@router.get("/{char_id}/blocks")
async def list_char_blocks(char_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT * FROM char_blocks WHERE character_id = ? ORDER BY position, rowid", (char_id,)
    ) as cur:
        blocks = [dict(r) for r in await cur.fetchall()]
    return await crud.attach_images(blocks, db)

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
    await db.execute(f"UPDATE char_blocks SET {cols} WHERE id = ? AND character_id = ?", vals)
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

@router.post("/{char_id}/blocks/{block_id}/images", status_code=201)
async def add_char_block_image(
    char_id: str,
    block_id: str,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    await crud.verify_entity_exists(db, "char_blocks", block_id, "character_id", char_id)
    try:
        return await crud.upload_block_image(
            db,
            block_id,
            "char",
            await file.read(),
            file.filename,
            file.content_type,
            str(CHARACTERS_DIR / char_id / "blocks"),
            images_only=True,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to save image: {str(e)}")

@router.delete("/{char_id}/blocks/{block_id}/images/{image_id}", status_code=204)
async def delete_char_block_image(
    char_id: str,
    block_id: str,
    image_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    await crud.delete_block_image(db, image_id, block_id)
