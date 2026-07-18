import aiosqlite
from fastapi import APIRouter, Depends

from focus.core.database import get_db
from focus.core.models import ActiveProviderUpdate, SettingsUpdate

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
