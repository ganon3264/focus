from fastapi import APIRouter, Depends

import focus.db as db
from focus.core.database import get_db
from focus.core.models import ActiveProviderUpdate, SettingsUpdate

router = APIRouter()


@router.get("/")
async def get_settings(_db=Depends(get_db)):
    async with _db.execute("SELECT key, value FROM settings") as cur:
        rows = await cur.fetchall()
    return {r["key"]: r["value"] for r in rows}


@router.patch("/")
async def update_setting(body: SettingsUpdate, _db=Depends(get_db)):
    await db.upsert_setting(_db, body.key, body.value)
    await _db.commit()
    return {"ok": True}


@router.get("/active-provider")
async def get_active_provider(_db=Depends(get_db)):
    async with _db.execute("SELECT value FROM settings WHERE key = 'active_provider_id'") as cur:
        row = await cur.fetchone()
    provider_id = row["value"] if row else None

    async with _db.execute("SELECT value FROM settings WHERE key = 'active_provider_type'") as cur:
        row = await cur.fetchone()
    provider_type = row["value"] if row else None

    return {"provider_id": provider_id, "provider_type": provider_type}


@router.put("/active-provider")
async def set_active_provider(body: ActiveProviderUpdate, _db=Depends(get_db)):
    await db.set_active_provider(_db, body.provider_id, body.provider_type)
    await _db.commit()
    return {"ok": True}
