import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

import focus.crud as crud
import focus.db as db
from focus.core.database import get_db
from focus.core.models import PresetBlockBulkUpdate, PresetBlockCreate, PresetUpdate
from focus.core.paths import PRESETS_DIR
from focus.core.utils import read_upload

router = APIRouter()


@router.post("/", status_code=201)
async def create_preset(name: str = Form(...), _db=Depends(get_db)):
    preset_id = await db.create_preset(_db, name)
    await _db.commit()
    return {"id": preset_id}


@router.get("/")
async def list_presets(_db=Depends(get_db)):
    async with _db.execute("SELECT id, name, created_at FROM presets ORDER BY name") as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/{preset_id}")
async def get_preset(preset_id: str, _db=Depends(get_db)):
    async with _db.execute("SELECT * FROM presets WHERE id = ?", (preset_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Preset not found")

    async with _db.execute(
        "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid", (preset_id,)
    ) as cur:
        blocks = [dict(r) for r in await cur.fetchall()]
    await crud.attach_images(blocks, _db)

    result = dict(row)
    result["blocks"] = blocks
    return result


@router.patch("/{preset_id}")
async def update_preset(
    preset_id: str,
    body: PresetUpdate,
    _db=Depends(get_db),
):
    await db.update_preset(_db, preset_id, body.name)
    await _db.commit()
    return {"ok": True}


@router.delete("/{preset_id}", status_code=204)
async def delete_preset(preset_id: str, _db=Depends(get_db)):
    await db.delete_preset(_db, preset_id)
    await _db.commit()


@router.post("/import", status_code=201)
async def import_preset(file: UploadFile = File(...), _db=Depends(get_db)):
    """Import a preset from an uploaded JSON file."""
    content = await read_upload(file)
    try:
        result = await db.import_preset(_db, content, file.filename)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(400, f"Invalid JSON in preset file: {e}")
    await _db.commit()
    return result


@router.post("/{preset_id}/blocks", status_code=201)
async def add_block(
    preset_id: str,
    body: PresetBlockCreate,
    _db=Depends(get_db),
):
    result = await db.create_preset_block(
        _db, preset_id, body.name, body.content, body.reasoning,
        body.role, body.enabled, body.block_type,
        body.injection_depth, body.injection_order,
    )
    await _db.commit()
    return result


@router.put("/{preset_id}/blocks")
async def replace_blocks(
    preset_id: str,
    body: PresetBlockBulkUpdate,
    _db=Depends(get_db),
):
    if not body.blocks:
        return {"ok": True}
    await db.replace_preset_blocks(_db, preset_id, body.blocks)
    await _db.commit()
    return {"ok": True}


@router.get("/{preset_id}/blocks/{block_id}")
async def get_block(
    preset_id: str,
    block_id: str,
    _db=Depends(get_db),
):
    async with _db.execute(
        "SELECT * FROM preset_blocks WHERE id = ? AND preset_id = ?",
        (block_id, preset_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Block not found")
    return dict(row)


@router.patch("/{preset_id}/blocks/{block_id}")
async def patch_block(
    preset_id: str,
    block_id: str,
    body: dict,
    _db=Depends(get_db),
):
    await db.update_preset_block(_db, preset_id, block_id, body)
    await _db.commit()
    return {"ok": True}


@router.delete("/{preset_id}/blocks/{block_id}", status_code=204)
async def delete_block(
    preset_id: str,
    block_id: str,
    _db=Depends(get_db),
):
    await db.delete_preset_block(_db, preset_id, block_id)
    await _db.commit()


@router.post("/{preset_id}/blocks/{block_id}/images", status_code=201)
async def add_block_image(
    preset_id: str,
    block_id: str,
    file: UploadFile = File(...),
    _db=Depends(get_db),
):
    await crud.verify_entity_exists(_db, "preset_blocks", block_id, "preset_id", preset_id)
    try:
        return await db.upload_block_image(
            _db,
            block_id,
            "preset",
            await read_upload(file),
            file.filename,
            file.content_type,
            str(PRESETS_DIR / preset_id / "blocks"),
            images_only=True,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to save image: {str(e)}")


@router.delete("/{preset_id}/blocks/{block_id}/images/{image_id}", status_code=204)
async def delete_block_image(
    preset_id: str,
    block_id: str,
    image_id: str,
    _db=Depends(get_db),
):
    await db.delete_block_image(_db, image_id, block_id)
