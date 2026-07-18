import json
from datetime import UTC, datetime

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from focus.core.database import get_db
from focus.core.models import ActiveProviderUpdate, SamplerConfigUpdate, SettingsUpdate
from focus.core.utils import now_iso

router = APIRouter()


@router.get("/")
async def get_settings(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT key, value FROM settings") as cur:
        rows = await cur.fetchall()
    return {r["key"]: r["value"] for r in rows}


@router.patch("/")
async def update_setting(body: SettingsUpdate, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (body.key, body.value),
    )
    await db.commit()
    return {"ok": True}


@router.get("/active-provider")
async def get_active_provider(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT value FROM settings WHERE key = 'active_provider_id'") as cur:
        row = await cur.fetchone()
    provider_id = row["value"] if row else None

    async with db.execute("SELECT value FROM settings WHERE key = 'active_provider_type'") as cur:
        row = await cur.fetchone()
    provider_type = row["value"] if row else None

    return {"provider_id": provider_id, "provider_type": provider_type}


@router.put("/active-provider")
async def set_active_provider(body: ActiveProviderUpdate, db: aiosqlite.Connection = Depends(get_db)):
    if body.provider_id:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES ('active_provider_id', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (body.provider_id,),
        )
    else:
        await db.execute("DELETE FROM settings WHERE key = 'active_provider_id'")

    if body.provider_type:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES ('active_provider_type', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (body.provider_type,),
        )
    else:
        await db.execute("DELETE FROM settings WHERE key = 'active_provider_type'")

    await db.commit()
    return {"ok": True}


@router.get("/samplers/{preset_id}")
async def get_sampler_config(
    preset_id: str,
    provider_id: str = "",
    db: aiosqlite.Connection = Depends(get_db),
):
    if not provider_id:
        return {"samplers": {}, "custom_fields": []}

    async with db.execute(
        "SELECT samplers, custom_fields FROM preset_sampler_configs WHERE preset_id = ? AND provider_id = ?",
        (preset_id, provider_id),
    ) as cur:
        row = await cur.fetchone()

    if row:
        return {
            "samplers": json.loads(row["samplers"]),
            "custom_fields": json.loads(row["custom_fields"]),
        }

    return {"samplers": {}, "custom_fields": []}


@router.put("/samplers/{preset_id}")
async def set_sampler_config(
    preset_id: str,
    body: SamplerConfigUpdate,
    db: aiosqlite.Connection = Depends(get_db),
):
    now = now_iso()
    await db.execute(
        """INSERT INTO preset_sampler_configs (preset_id, provider_id, samplers, custom_fields, updated_at)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(preset_id, provider_id) DO UPDATE SET
               samplers = excluded.samplers,
               custom_fields = excluded.custom_fields,
               updated_at = excluded.updated_at""",
        (
            preset_id,
            body.provider_id,
            json.dumps(body.samplers),
            json.dumps(body.custom_fields),
            now,
        ),
    )
    await db.commit()
    return {"ok": True}
