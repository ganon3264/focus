import json
import uuid
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File

import pyvern.crud as crud
from pyvern.database import get_db
from pyvern.models import PresetCreate, PresetUpdate, PresetBlockCreate, PresetBlockBulkUpdate
from pyvern.utils import now_iso, variable_group_name

router = APIRouter()


# ── Presets ───────────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
async def create_preset(body: PresetCreate, db: aiosqlite.Connection = Depends(get_db)):
    preset_id = str(uuid.uuid4())
    now = now_iso()

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
    await crud.attach_images(blocks, db)

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


@router.post("/import", status_code=201)
async def import_preset(file: UploadFile = File(...), db: aiosqlite.Connection = Depends(get_db)):
    """Import a preset from an uploaded JSON file."""
    content = await file.read()
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise HTTPException(400, f"Invalid JSON in preset file: {e}")

    preset_name = Path(file.filename or "Imported Preset").stem
    preset_id = str(uuid.uuid4())
    now = now_iso()
    await db.execute(
        "INSERT INTO presets (id, name, created_at) VALUES (?, ?, ?)",
        (preset_id, preset_name, now),
    )

    SENTINEL_MAP = {
        "chatHistory": "chat_history",
        "charDescription": "char_description",
        "charPersonality": "char_personality",
        "personaDescription": "user_persona",
    }

    prompts = data.get("prompts", [])
    prompt_order = data.get("prompt_order", [])

    enabled_map: dict[str, bool] = {}
    order_list: list[str] = []
    if prompt_order:
        best_profile = max(prompt_order, key=lambda p: len(p.get("order", [])))
        for entry in best_profile.get("order", []):
            ident = entry["identifier"]
            enabled_map[ident] = entry.get("enabled", True)
            order_list.append(ident)

    # Build blocks from prompts, keeping identifier for reordering
    block_map: dict[str, dict] = {}
    blocks_in_order: list[dict] = []

    for prompt in prompts:
        identifier = prompt.get("identifier", "")
        block_type = SENTINEL_MAP.get(identifier, "text")

        enabled = enabled_map.get(identifier)
        if enabled is None:
            enabled = prompt.get("enabled", True)

        is_in_chat = prompt.get("system_prompt") is False
        block = {
            "id": str(uuid.uuid4()),
            "preset_id": preset_id,
            "name": prompt.get("name") or identifier,
            "content": prompt.get("content", ""),
            "role": prompt.get("role", "system"),
            "enabled": int(enabled),
            "position": 0.0,
            "block_type": block_type,
            "injection_depth": prompt.get("injection_depth") if is_in_chat else None,
            "injection_order": prompt.get("injection_order", 0) if is_in_chat else 0,
        }
        block_map[identifier] = block

    # Position blocks: prompt_order sequence first, then remaining in prompts order
    seen: set[str] = set()
    for ident in order_list:
        if ident in block_map and ident not in seen:
            blocks_in_order.append(block_map[ident])
            seen.add(ident)
    for prompt in prompts:
        ident = prompt.get("identifier", "")
        if ident not in seen:
            blocks_in_order.append(block_map[ident])
            seen.add(ident)

    pos = 0.0
    for b in blocks_in_order:
        pos += 1.0
        b["position"] = pos
        await db.execute(
            """INSERT INTO preset_blocks
               (id, preset_id, name, content, role, enabled, position, block_type, injection_depth, injection_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (b["id"], b["preset_id"], b["name"], b["content"], b["role"],
             b["enabled"], b["position"], b["block_type"], b["injection_depth"], b["injection_order"]),
        )

    await db.commit()
    return {"id": preset_id, "name": preset_name, "block_count": len(blocks_in_order)}


# ── Block management ──────────────────────────────────────────────────────────

@router.post("/{preset_id}/blocks", status_code=201)
async def add_block(
    preset_id: str,
    body: PresetBlockCreate,
    db: aiosqlite.Connection = Depends(get_db),
):
    block_id = str(uuid.uuid4())
    next_pos = await crud.next_position(db, "preset_blocks", "preset_id", preset_id)

    await db.execute(
        """INSERT INTO preset_blocks
           (id, preset_id, name, content, role, enabled, position, block_type, injection_depth, injection_order)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (block_id, preset_id, body.name, body.content, body.role,
         int(body.enabled), next_pos, body.block_type, body.injection_depth, body.injection_order),
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
    allowed = {"name", "content", "role", "enabled", "position", "injection_depth", "injection_order"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        return {"ok": True}
        
    # Check mutual exclusivity for variable blocks
    if "enabled" in updates and updates["enabled"]:
        async with db.execute("SELECT name, block_type FROM preset_blocks WHERE id = ? AND preset_id = ?", (block_id, preset_id)) as cur:
            block_row = await cur.fetchone()
        
        if block_row and block_row["block_type"] == "variable":
            group_name = variable_group_name(block_row["name"])
            await db.execute(
                "UPDATE preset_blocks SET enabled = 0 WHERE preset_id = ? AND block_type = 'variable' AND id != ? AND (name = ? OR name LIKE ?)",
                (preset_id, block_id, group_name, f"{group_name}:%")
            )

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
    async with db.execute(
        "SELECT id FROM preset_blocks WHERE id = ? AND preset_id = ?", (block_id, preset_id)
    ) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Block not found")

    try:
        return await crud.upload_block_image(db, block_id, "preset", await file.read(), file.filename, file.content_type, f"assets/presets/{preset_id}/blocks", images_only=True)
    except Exception as e:
        raise HTTPException(500, f"Failed to save image: {str(e)}")


@router.delete("/{preset_id}/blocks/{block_id}/images/{image_id}", status_code=204)
async def delete_block_image(
    preset_id: str,
    block_id: str,
    image_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    await crud.delete_block_image(db, image_id, block_id)
