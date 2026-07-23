import json
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

import focus.crud as crud
import focus.db as db
from focus.core.card_parser import normalise_card, parse_card_bytes, validate_card_warnings
from focus.core.database import get_db
from focus.core.models import CharacterCreate, CharacterUpdate, CharBlockCreate, CharBlockUpdate
from focus.core.paths import BLOCKS_DIR, CHARACTERS_DIR
from focus.core.utils import read_upload

router = APIRouter()
logger = logging.getLogger("focus.routers.characters")


@router.post("/import", status_code=201)
async def import_character(
    files: list[UploadFile] = File(...),
    _db=Depends(get_db),
):
    imported = []
    errors = []

    for file in files:
        try:
            entry = await db.import_character(_db, await read_upload(file), file.filename)
        except ValueError as e:
            errors.append({"filename": file.filename, "error": str(e)})
            continue
        except Exception as e:
            errors.append({"filename": file.filename, "error": f"Invalid card format: {e}"})
            continue

        imported.append(entry)

    await _db.commit()

    result = {"imported": imported, "total": len(imported) + len(errors)}
    if errors:
        result["errors"] = errors
    return result


@router.post("/", status_code=201)
async def create_character(body: CharacterCreate, _db=Depends(get_db)):
    char_id = await db.create_character(
        _db, body.name, body.description, body.personality,
        body.scenario, body.mes_example, body.first_mes,
        body.alternate_greetings,
    )
    await _db.commit()
    return {"id": char_id, "name": body.name}


@router.patch("/{char_id}")
async def update_character(
    char_id: str,
    body: CharacterUpdate,
    _db=Depends(get_db),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"ok": True}
    await db.update_character(_db, char_id, updates)
    await _db.commit()
    return {"ok": True}


@router.post("/{char_id}/avatar")
async def upload_avatar(
    char_id: str,
    file: UploadFile = File(...),
    _db=Depends(get_db),
):
    async with _db.execute("SELECT image_path FROM characters WHERE id = ?", (char_id,)) as cur:
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
        Path(avatar_path).write_bytes(await read_upload(file))
    except OSError as e:
        raise HTTPException(500, f"Failed to save avatar: {e}")

    await db.update_character_avatar(_db, char_id, avatar_path)
    await _db.commit()
    return {"avatar_path": avatar_path}


@router.get("/")
async def list_characters(_db=Depends(get_db)):
    async with _db.execute(
        "SELECT id, name, image_path, created_at FROM characters WHERE is_deleted = 0 ORDER BY name"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/trash")
async def list_trashed_characters(_db=Depends(get_db)):
    async with _db.execute(
        "SELECT id, name, image_path, created_at FROM characters WHERE is_deleted = 1 ORDER BY name"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/{char_id}")
async def get_character(char_id: str, _db=Depends(get_db)):
    async with _db.execute("SELECT * FROM characters WHERE id = ?", (char_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Character not found")

    blocks = await crud.load_entity_blocks(_db, "char_blocks", "character_id", char_id)

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
    _db=Depends(get_db),
):
    if hard:
        avatar_path = await db.hard_delete_character(_db, char_id)
        if avatar_path:
            Path(avatar_path).unlink(missing_ok=True)
        shutil.rmtree(CHARACTERS_DIR / char_id, ignore_errors=True)
    else:
        avatar_path = await db.delete_character(_db, char_id, delete_chats)
        if avatar_path:
            Path(avatar_path).unlink(missing_ok=True)
    await _db.commit()


@router.post("/{char_id}/restore", status_code=200)
async def restore_character(char_id: str, restore_chats: bool = False, _db=Depends(get_db)):
    await db.restore_character(_db, char_id, restore_chats)
    await _db.commit()
    return {"ok": True}


@router.post("/{char_id}/images", status_code=201)
async def add_char_image(
    char_id: str,
    file: UploadFile = File(...),
    _db=Depends(get_db),
):
    await crud.verify_entity_exists(_db, "characters", char_id)
    try:
        return await db.upload_block_image(
            _db,
            char_id,
            "char",
            await read_upload(file),
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
    _db=Depends(get_db),
):
    await db.delete_block_image(_db, image_id, char_id)


@router.get("/{char_id}/blocks")
async def list_char_blocks(char_id: str, _db=Depends(get_db)):
    async with _db.execute(
        "SELECT * FROM char_blocks WHERE character_id = ? ORDER BY position, rowid", (char_id,)
    ) as cur:
        blocks = [dict(r) for r in await cur.fetchall()]
    return await crud.attach_images(blocks, _db)


@router.post("/{char_id}/blocks", status_code=201)
async def create_char_block(
    char_id: str,
    body: CharBlockCreate,
    _db=Depends(get_db),
):
    block_id = await db.create_char_block(
        _db, char_id, body.name, body.content, body.role, body.enabled, body.position,
    )
    await _db.commit()
    return {"id": block_id}


@router.patch("/{char_id}/blocks/{block_id}")
async def update_char_block(
    char_id: str,
    block_id: str,
    body: CharBlockUpdate,
    _db=Depends(get_db),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"ok": True}
    await db.update_char_block(_db, char_id, block_id, updates)
    await _db.commit()
    return {"ok": True}


@router.delete("/{char_id}/blocks/{block_id}", status_code=204)
async def delete_char_block(
    char_id: str,
    block_id: str,
    _db=Depends(get_db),
):
    await db.delete_char_block(_db, char_id, block_id)
    await _db.commit()


@router.post("/{char_id}/blocks/{block_id}/images", status_code=201)
async def add_char_block_image(
    char_id: str,
    block_id: str,
    file: UploadFile = File(...),
    _db=Depends(get_db),
):
    await crud.verify_entity_exists(_db, "char_blocks", block_id, "character_id", char_id)
    try:
        return await db.upload_block_image(
            _db,
            block_id,
            "character",
            await read_upload(file),
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
    _db=Depends(get_db),
):
    await db.delete_block_image(_db, image_id, block_id)
