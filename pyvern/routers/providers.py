import json
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from pyvern.database import get_db
from pyvern.models import ProviderCreate

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.post("/", status_code=201)
async def create_provider(body: ProviderCreate, db: aiosqlite.Connection = Depends(get_db)):
    provider_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO providers (id, name, type, base_url, api_key, model, params_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (provider_id, body.name, body.type, body.base_url, body.api_key,
         body.model, json.dumps(body.params), _now()),
    )
    await db.commit()
    return {"id": provider_id}


@router.get("/")
async def list_providers(db: aiosqlite.Connection = Depends(get_db)):
    # Never return api_key
    async with db.execute(
        "SELECT id, name, type, base_url, model, created_at FROM providers ORDER BY name"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.patch("/{provider_id}")
async def update_provider(
    provider_id: str,
    body: dict,
    db: aiosqlite.Connection = Depends(get_db),
):
    allowed = {"name", "base_url", "api_key", "model", "params_json"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if "params" in body:
        updates["params_json"] = json.dumps(body["params"])
    if not updates:
        return {"ok": True}
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [provider_id]
    await db.execute(f"UPDATE providers SET {cols} WHERE id = ?", vals)
    await db.commit()
    return {"ok": True}


@router.delete("/{provider_id}", status_code=204)
async def delete_provider(provider_id: str, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))
    await db.commit()
