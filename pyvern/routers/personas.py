import uuid
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional

import pyvern.crud as crud
from pyvern.database import get_db
from pyvern.utils import now_iso

router = APIRouter()


class PersonaCreate(BaseModel):
    name: str
    description: str = ""


class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None


@router.get("/")
async def list_personas(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM personas ORDER BY name") as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.post("/", status_code=201)
async def create_persona(body: PersonaCreate, db: aiosqlite.Connection = Depends(get_db)):
    persona_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO personas (id, name, description, avatar_path, created_at) VALUES (?, ?, ?, ?, ?)",
        (persona_id, body.name, body.description, None, now_iso()),
    )
    await db.commit()
    return {"id": persona_id}


@router.get("/{persona_id}")
async def get_persona(persona_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Persona not found")
    return dict(row)


@router.patch("/{persona_id}")
async def update_persona(
    persona_id: str,
    body: PersonaUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    updates = body.model_dump(exclude_none=True)
    if not updates:
        return {"ok": True}
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [persona_id]
    await db.execute(f"UPDATE personas SET {cols} WHERE id = ?", vals)
    await db.commit()
    return {"ok": True}


@router.post("/{persona_id}/avatar", status_code=200)
async def upload_avatar(
    persona_id: str,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("SELECT avatar_path FROM personas WHERE id = ?", (persona_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Persona not found")

    # Remove old avatar if present
    if row["avatar_path"]:
        Path(row["avatar_path"]).unlink(missing_ok=True)

    suffix = Path(file.filename).suffix or ".png"
    persona_dir = Path(f"assets/personas/{persona_id}")
    persona_dir.mkdir(parents=True, exist_ok=True)
    avatar_path = str(persona_dir / f"avatar{suffix}")
    try:
        Path(avatar_path).write_bytes(await file.read())
    except OSError as e:
        raise HTTPException(500, f"Failed to save avatar: {e}")

    await db.execute("UPDATE personas SET avatar_path = ? WHERE id = ?", (avatar_path, persona_id))
    await db.commit()
    return {"avatar_path": avatar_path}


@router.delete("/{persona_id}", status_code=204)
async def delete_persona(persona_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT avatar_path, name FROM personas WHERE id = ?", (persona_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Persona not found")
    if row["name"] == "User":
        raise HTTPException(400, "Cannot delete the default persona")

    if row["avatar_path"]:
        Path(row["avatar_path"]).unlink(missing_ok=True)

    await db.execute("DELETE FROM personas WHERE id = ?", (persona_id,))
    await db.commit()


@router.post("/{persona_id}/images", status_code=201)
async def add_persona_image(
    persona_id: str,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    await crud.verify_entity_exists(db, "personas", persona_id)
    try:
        return await crud.upload_block_image(db, persona_id, "char", await file.read(), file.filename, file.content_type, "assets/blocks", images_only=False)
    except Exception as e:
        raise HTTPException(500, f"Failed to save image: {str(e)}")


@router.delete("/{persona_id}/images/{image_id}", status_code=204)
async def delete_persona_image(
    persona_id: str,
    image_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    await crud.delete_block_image(db, image_id, persona_id)
