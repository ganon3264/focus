import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

from pyvern.database import get_db
from pyvern.models import PresetCreate, PresetUpdate, PresetBlockCreate, PresetBlockBulkUpdate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _attach_images(blocks: list[dict], db: aiosqlite.Connection) -> list[dict]:
    if not blocks:
        return blocks
    ids = [b["id"] for b in blocks]
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT id, block_id, image_path, mime_type, position FROM block_images WHERE block_id IN ({placeholders}) ORDER BY position",
        ids,
    ) as cur:
        rows = await cur.fetchall()
    images_by_block: dict[str, list] = {}
    for r in rows:
        images_by_block.setdefault(r["block_id"], []).append(dict(r))
    for b in blocks:
        b["images"] = images_by_block.get(b["id"], [])
    return blocks


# ── Presets ───────────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
async def create_preset(body: PresetCreate, db: aiosqlite.Connection = Depends(get_db)):
    preset_id = str(uuid.uuid4())
    now = _now()

    await db.execute(
        "INSERT INTO presets (id, name, created_at) VALUES (?, ?, ?)",
        (preset_id, body.name, now),
    )

    # Seed with sensible default blocks
    defaults = [
        (str(uuid.uuid4()), preset_id, "System Prompt", "A default system prompt (please replace it!)", "system", 1, 0.0, "text"),
        (str(uuid.uuid4()), preset_id, "Char Description", "", "user", 1, 1.0, "char_description"),
        (str(uuid.uuid4()), preset_id, "User Persona", "", "user", 1, 2.0, "user_persona"),
        (str(uuid.uuid4()), preset_id, "Char Blocks", "", "system", 1, 3.0, "char_blocks"),
        (str(uuid.uuid4()), preset_id, "Chat History", "", "system", 1, 4.0, "chat_history"),
    ]
    await db.executemany(
        "INSERT INTO preset_blocks (id, preset_id, name, content, role, enabled, position, block_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        defaults,
    )
    await db.commit()
    return {"id": preset_id}


@router.get("/")
async def list_presets(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT id, name, created_at FROM presets ORDER BY name") as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/{preset_id}")
async def get_preset(preset_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM presets WHERE id = ?", (preset_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Preset not found")

    async with db.execute(
        "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid", (preset_id,)
    ) as cur:
        blocks = [dict(r) for r in await cur.fetchall()]
    await _attach_images(blocks, db)

    result = dict(row)
    result["blocks"] = blocks
    return result

@router.patch("/{preset_id}")
async def update_preset(
    preset_id: str,
    body: PresetUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    await db.execute(
        "UPDATE presets SET name = ? WHERE id = ?", (body.name, preset_id)
    )
    await db.commit()
    return {"ok": True}

@router.delete("/{preset_id}", status_code=204)
async def delete_preset(preset_id: str, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM presets WHERE id = ?", (preset_id,))
    await db.commit()


# ── Block management ──────────────────────────────────────────────────────────

@router.post("/{preset_id}/blocks", status_code=201)
async def add_block(
    preset_id: str,
    body: PresetBlockCreate,
    db: aiosqlite.Connection = Depends(get_db),
):
    block_id = str(uuid.uuid4())
    async with db.execute(
        "SELECT COALESCE(MAX(position), -1) FROM preset_blocks WHERE preset_id = ?", (preset_id,)
    ) as cur:
        row = await cur.fetchone()
    next_pos = row[0] + 1

    await db.execute(
        """INSERT INTO preset_blocks
           (id, preset_id, name, content, role, enabled, position, block_type)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (block_id, preset_id, body.name, body.content, body.role,
         int(body.enabled), next_pos, body.block_type),
    )
    await db.commit()
    return {"id": block_id, "position": next_pos}


@router.put("/{preset_id}/blocks")
async def replace_blocks(
    preset_id: str,
    body: PresetBlockBulkUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    if not body.blocks:
        return {"ok": True}

    block_ids = [b["id"] for b in body.blocks]
    placeholders = ",".join("?" * len(block_ids))

    # Verify all blocks belong to this preset
    async with db.execute(
        f"SELECT id FROM preset_blocks WHERE id IN ({placeholders}) AND preset_id = ?",
        (*block_ids, preset_id),
    ) as cur:
        found = {r["id"] for r in await cur.fetchall()}

    missing = set(block_ids) - found
    if missing:
        raise HTTPException(400, detail=f"Blocks not found: {missing}")

    # Update only positions — no delete, no insert
    for b in body.blocks:
        await db.execute(
            "UPDATE preset_blocks SET position = ? WHERE id = ? AND preset_id = ?",
            (b["position"], b["id"], preset_id),
        )

    await db.commit()
    return {"ok": True}


@router.patch("/{preset_id}/blocks/{block_id}")
async def patch_block(
    preset_id: str,
    block_id: str,
    body: dict,
    db: aiosqlite.Connection = Depends(get_db),
):
    allowed = {"name", "content", "role", "enabled", "position"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return {"ok": True}
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [block_id, preset_id]
    await db.execute(
        f"UPDATE preset_blocks SET {cols} WHERE id = ? AND preset_id = ?", vals
    )
    await db.commit()
    return {"ok": True}


@router.delete("/{preset_id}/blocks/{block_id}", status_code=204)
async def delete_block(
    preset_id: str,
    block_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    await db.execute(
        "DELETE FROM preset_blocks WHERE id = ? AND preset_id = ?", (block_id, preset_id)
    )
    await db.commit()


# ── Block images ──────────────────────────────────────────────────────────────

@router.post("/{preset_id}/blocks/{block_id}/images", status_code=201)
async def add_block_image(
    preset_id: str,
    block_id: str,
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    # Verify block belongs to preset
    async with db.execute(
        "SELECT id FROM preset_blocks WHERE id = ? AND preset_id = ?", (block_id, preset_id)
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Block not found")

    async with db.execute(
        "SELECT COALESCE(MAX(position), -1) FROM block_images WHERE block_id = ?", (block_id,)
    ) as cur:
        row = await cur.fetchone()
    next_pos = row[0] + 1

    image_id = str(uuid.uuid4())
    suffix = Path(file.filename).suffix.lower() or ".png"
    mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".gif": "image/gif", ".webp": "image/webp"}.get(suffix, "image/png")
    blocks_dir = Path(f"assets/presets/{preset_id}/blocks")
    blocks_dir.mkdir(parents=True, exist_ok=True)
    image_path = str(blocks_dir / f"{image_id}{suffix}")
    Path(image_path).write_bytes(await file.read())

    await db.execute(
        "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (image_id, block_id, "preset", image_path, mime, next_pos, _now()),
    )
    await db.commit()
    return {"id": image_id, "position": next_pos}


@router.delete("/{preset_id}/blocks/{block_id}/images/{image_id}", status_code=204)
async def delete_block_image(
    preset_id: str,
    block_id: str,
    image_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT image_path FROM block_images WHERE id = ? AND block_id = ?", (image_id, block_id)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Image not found")
    Path(row["image_path"]).unlink(missing_ok=True)
    await db.execute("DELETE FROM block_images WHERE id = ?", (image_id,))
    await db.commit()
