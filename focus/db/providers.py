from __future__ import annotations

import json
import uuid

import aiosqlite

from focus.core.utils import now_iso, resolve_secret_key


async def create_provider(
    db: aiosqlite.Connection,
    name: str,
    type: str,
    base_url: str | None,
    api_key: str | None,
    model: str,
    params: dict | None = None,
) -> str:
    provider_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO providers (id, name, type, base_url, api_key, model, params_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (provider_id, name, type, base_url, api_key, model, json.dumps(params or {}), now_iso()),
    )
    return provider_id


async def update_provider(db: aiosqlite.Connection, provider_id: str, updates: dict) -> None:
    allowed = {"name", "base_url", "api_key", "model", "params_json"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    if "api_key" in updates and not updates["api_key"]:
        del updates["api_key"]
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [provider_id]
    await db.execute(f"UPDATE providers SET {cols} WHERE id = ?", vals)


async def delete_provider(db: aiosqlite.Connection, provider_id: str) -> None:
    await db.execute("DELETE FROM providers WHERE id = ?", (provider_id,))


async def upsert_secret(db: aiosqlite.Connection, name: str, value: str) -> None:
    if not value:
        await db.execute("DELETE FROM secrets WHERE name = ?", (name,))
    else:
        await db.execute(
            "INSERT INTO secrets (name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (name, value),
        )


async def delete_secret(db: aiosqlite.Connection, name: str) -> None:
    await db.execute("DELETE FROM secrets WHERE name = ?", (name,))


def _parse_params(params_json: str | None) -> dict:
    try:
        params = json.loads(params_json or "{}")
    except json.JSONDecodeError:
        return {}
    return params if isinstance(params, dict) else {}


def provider_key_refs(row: dict) -> list[str]:
    """Ordered key refs for a provider.

    ``params.api_keys`` is authoritative when it holds at least one usable
    entry; otherwise the legacy single ``api_key`` column is a one-element
    fallback. A ref is either ``SECRET:<name>`` or a literal key.
    """
    refs = _parse_params(row.get("params_json")).get("api_keys")
    if isinstance(refs, list):
        cleaned = [r for r in refs if isinstance(r, str) and r]
        if cleaned:
            return cleaned
    legacy = row.get("api_key")
    return [legacy] if legacy else []


def active_key_ref(row: dict) -> str | None:
    """The selected ref, falling back to the first key."""
    refs = provider_key_refs(row)
    if not refs:
        return None
    active = _parse_params(row.get("params_json")).get("active_key")
    return active if active in refs else refs[0]


async def resolve_active_api_key(db: aiosqlite.Connection, row: dict) -> str:
    """Resolve the active key's secret to its usable value."""
    ref = active_key_ref(row)
    return await resolve_secret_key(db, ref) if ref else ""


async def set_active_key(db: aiosqlite.Connection, provider_id: str, ref: str) -> bool:
    """Select *ref* as the active key.

    Returns False if the provider is missing or *ref* is not one of its keys.
    """
    async with db.execute(
        "SELECT params_json, api_key FROM providers WHERE id = ?", (provider_id,)
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return False
    row = dict(row)
    if ref not in provider_key_refs(row):
        return False
    params = _parse_params(row.get("params_json"))
    params["active_key"] = ref
    await db.execute(
        "UPDATE providers SET params_json = ? WHERE id = ?",
        (json.dumps(params), provider_id),
    )
    return True
