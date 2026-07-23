import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

import focus.crud as crud
import focus.db as db
from focus.core.database import get_db
from focus.core.paths import BLOCKS_DIR, PERSONAS_DIR
from focus.core.utils import read_upload

router = APIRouter()


class PersonaCreate(BaseModel):
    name: str
    description: str = ""


class PersonaUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


@router.get("/")
async def list_personas(_db=Depends(get_db)):
    async with _db.execute("SELECT * FROM personas WHERE is_deleted = 0 ORDER BY name") as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/trash")
async def list_trashed_personas(_db=Depends(get_db)):
    async with _db.execute(
        "SELECT id, name, avatar_path, created_at FROM personas WHERE is_deleted = 1 ORDER BY name"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.post("/", status_code=201)
async def create_persona(body: PersonaCreate, _db=Depends(get_db)):
    persona_id = await db.create_persona(_db, body.name, body.description)
    await _db.commit()
    return {"id": persona_id}


@router.get("/{persona_id}")
async def get_persona(persona_id: str, _db=Depends(get_db)):
    async with _db.execute("SELECT * FROM personas WHERE id = ? AND is_deleted = 0", (persona_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Persona not found")
    return dict(row)


@router.patch("/{persona_id}")
async def update_persona(
    persona_id: str,
    body: PersonaUpdate,
    _db=Depends(get_db),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"ok": True}
    await db.update_persona(_db, persona_id, updates)
    await _db.commit()
    return {"ok": True}


@router.post("/{persona_id}/avatar", status_code=200)
async def upload_avatar(
    persona_id: str,
    file: UploadFile = File(...),
    _db=Depends(get_db),
):
    async with _db.execute("SELECT avatar_path FROM personas WHERE id = ?", (persona_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Persona not found")

    if row["avatar_path"]:
        Path(row["avatar_path"]).unlink(missing_ok=True)

    suffix = Path(file.filename).suffix or ".png"
    persona_dir = PERSONAS_DIR / persona_id
    persona_dir.mkdir(parents=True, exist_ok=True)
    avatar_path = str(persona_dir / f"avatar{suffix}")
    try:
        Path(avatar_path).write_bytes(await read_upload(file))
    except OSError as e:
        raise HTTPException(500, f"Failed to save avatar: {e}")

    await db.update_persona_avatar(_db, persona_id, avatar_path)
    await _db.commit()
    return {"avatar_path": avatar_path}


@router.delete("/{persona_id}", status_code=204)
async def delete_persona(
    persona_id: str,
    hard: bool = False,
    _db=Depends(get_db),
):
    async with _db.execute("SELECT name FROM personas WHERE id = ?", (persona_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Persona not found")
    if row["name"] == "User":
        raise HTTPException(400, "Cannot delete the default persona")

    if hard:
        avatar_path = await db.hard_delete_persona(_db, persona_id)
        if avatar_path:
            Path(avatar_path).unlink(missing_ok=True)
        shutil.rmtree(PERSONAS_DIR / persona_id, ignore_errors=True)
    else:
        await db.delete_persona(_db, persona_id)
    await _db.commit()


@router.post("/{persona_id}/restore", status_code=200)
async def restore_persona(persona_id: str, _db=Depends(get_db)):
    async with _db.execute("SELECT id FROM personas WHERE id = ?", (persona_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Persona not found")
    await db.restore_persona(_db, persona_id)
    await _db.commit()
    return {"ok": True}


@router.post("/{persona_id}/images", status_code=201)
async def add_persona_image(
    persona_id: str,
    file: UploadFile = File(...),
    _db=Depends(get_db),
):
    await crud.verify_entity_exists(_db, "personas", persona_id)
    try:
        return await db.upload_block_image(
            _db,
            persona_id,
            "persona",
            await read_upload(file),
            file.filename,
            file.content_type,
            str(BLOCKS_DIR),
            images_only=False,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to save image: {str(e)}")


@router.delete("/{persona_id}/images/{image_id}", status_code=204)
async def delete_persona_image(
    persona_id: str,
    image_id: str,
    _db=Depends(get_db),
):
    await db.delete_block_image(_db, image_id, persona_id)
