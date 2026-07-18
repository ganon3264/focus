import uuid
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from typing import Optional

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
    Path(avatar_path).write_bytes(await file.read())

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
    async with db.execute("SELECT id FROM personas WHERE id = ?", (persona_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Persona not found")

    async with db.execute(
        "SELECT COALESCE(MAX(position), -1) FROM block_images WHERE block_id = ?", (persona_id,)
    ) as cur:
        row = await cur.fetchone()
    next_pos = row[0] + 1

    image_id = str(uuid.uuid4())
    suffix = Path(file.filename).suffix.lower() or ".png"
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".gif": "image/gif", ".webp": "image/webp", ".mp3": "audio/mpeg", 
            ".wav": "audio/wav", ".ogg": "audio/ogg"}.get(suffix, "application/octet-stream")

    if mime == "application/octet-stream" and file.content_type:
        mime = file.content_type

    blocks_dir = Path("assets/blocks")
    blocks_dir.mkdir(parents=True, exist_ok=True)
    image_path = str(blocks_dir / f"{image_id}{suffix}")
    Path(image_path).write_bytes(await file.read())

    await db.execute(
        "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (image_id, persona_id, "char", image_path, mime, next_pos, now_iso()),
    )
    await db.commit()
    return {"id": image_id, "position": next_pos, "image_path": image_path, "mime_type": mime}


@router.delete("/{persona_id}/images/{image_id}", status_code=204)
async def delete_persona_image(
    persona_id: str,
    image_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT image_path FROM block_images WHERE id = ? AND block_id = ?", (image_id, persona_id)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Image not found")
    Path(row["image_path"]).unlink(missing_ok=True)
    await db.execute("DELETE FROM block_images WHERE id = ?", (image_id,))
    await db.commit()
