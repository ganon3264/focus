from __future__ import annotations

import aiosqlite


async def upsert_setting(db: aiosqlite.Connection, key: str, value: str) -> None:
    await db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


async def delete_setting(db: aiosqlite.Connection, key: str) -> None:
    await db.execute("DELETE FROM settings WHERE key = ?", (key,))


async def set_active_provider(
    db: aiosqlite.Connection,
    provider_id: str | None = None,
    provider_type: str | None = None,
) -> None:
    if provider_id:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES ('active_provider_id', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (provider_id,),
        )
    else:
        await db.execute("DELETE FROM settings WHERE key = 'active_provider_id'")

    if provider_type:
        await db.execute(
            "INSERT INTO settings (key, value) VALUES ('active_provider_type', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (provider_type,),
        )
    else:
        await db.execute("DELETE FROM settings WHERE key = 'active_provider_type'")
