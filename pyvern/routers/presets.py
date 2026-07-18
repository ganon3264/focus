import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from pyvern.database import get_db
from pyvern.models import PresetCreate, PresetBlockCreate, PresetBlockBulkUpdate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
        (str(uuid.uuid4()), preset_id, "System Prompt", "", "system", 1, 0.0, 0),
        (str(uuid.uuid4()), preset_id, "Char Description", "{{description}}", "system", 1, 1.0, 0),
        (str(uuid.uuid4()), preset_id, "Persona",          "{{personality}}", "system", 1, 2.0, 0),
        (str(uuid.uuid4()), preset_id, "Chat History",     "",                "system", 1, 3.0, 1),  # sentinel
    ]
    await db.executemany(
        "INSERT INTO preset_blocks (id, preset_id, name, content, role, enabled, position, is_sentinel) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
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
        "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position", (preset_id,)
    ) as cur:
        blocks = [dict(r) for r in await cur.fetchall()]

    result = dict(row)
    result["blocks"] = blocks
    return result


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
    await db.execute(
        """INSERT INTO preset_blocks
           (id, preset_id, name, content, role, enabled, position, is_sentinel, source, character_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (block_id, preset_id, body.name, body.content, body.role,
         int(body.enabled), body.position, int(body.is_sentinel),
         body.source, body.character_id),
    )
    await db.commit()
    return {"id": block_id}


@router.put("/{preset_id}/blocks")
async def replace_blocks(
    preset_id: str,
    body: PresetBlockBulkUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Replace all preset-source blocks atomically.
    Used for drag-reorder saves. Character-source blocks are untouched.
    """
    await db.execute(
        "DELETE FROM preset_blocks WHERE preset_id = ? AND source = 'preset'", (preset_id,)
    )
    for b in body.blocks:
        bid = b.get("id") or str(uuid.uuid4())
        await db.execute(
            """INSERT INTO preset_blocks
               (id, preset_id, name, content, role, enabled, position, is_sentinel, source, character_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bid, preset_id, b["name"], b.get("content", ""),
             b.get("role", "system"), int(b.get("enabled", True)),
             b["position"], int(b.get("is_sentinel", False)),
             "preset", b.get("character_id")),
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
