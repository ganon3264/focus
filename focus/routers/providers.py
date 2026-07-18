import json
import uuid

import aiosqlite
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from focus.database import get_db
from focus.logger import get_logger
from focus.models import ProviderCreate
from focus.utils import MODEL_FETCH_HTTP_TIMEOUT, TTLCache, now_iso, resolve_secret_key

router = APIRouter()
logger = get_logger("routers.providers")

@router.post("/", status_code=201)
async def create_provider(body: ProviderCreate, db: aiosqlite.Connection = Depends(get_db)):
    provider_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO providers (id, name, type, base_url, api_key, model, params_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            provider_id,
            body.name,
            body.type,
            body.base_url,
            body.api_key,
            body.model,
            json.dumps(body.params),
            now_iso(),
        ),
    )
    await db.commit()
    return {"id": provider_id}

@router.get("/")
async def list_providers(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT id, name, type, base_url, api_key, model, params_json, created_at FROM providers ORDER BY name"
    ) as cur:
        out = []
        for r in await cur.fetchall():
            d = dict(r)
            ak = d.get("api_key") or ""
            if ak.startswith("SECRET:"):
                pass
            elif ak:
                d["api_key"] = "__HIDDEN__"
            else:
                d["api_key"] = ""
            out.append(d)
        return out

@router.patch("/{provider_id}")
async def update_provider(
    provider_id: str,
    body: dict,
    db: aiosqlite.Connection = Depends(get_db),
):
    allowed = {"name", "base_url", "api_key", "model", "params_json"}
    updates = {k: v for k, v in body.items() if k in allowed}

    # Don't overwrite api_key with empty string (unless explicitly clearing it, which the UI doesn't support for existing keys)
    if "api_key" in updates and not updates["api_key"]:
        del updates["api_key"]

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

from focus.providers import create_provider as provider_factory

_model_cache = TTLCache()
_or_cache = TTLCache()

class FetchModelsRequest(BaseModel):
    type: str
    base_url: str | None = None
    api_key: str | None = None
    params: dict = {}

@router.post("/fetch_models")
async def fetch_models(body: FetchModelsRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Fetch available models from a provider and cache the result for 5 minutes."""
    api_key = await resolve_secret_key(db, body.api_key or "")

    # Cache key based on provider type and api key hash (to avoid caching across different keys)
    cache_key = f"{body.type}_{hash(api_key)}"
    cached = await _model_cache.get(cache_key)
    if cached is not None:
        return {"data": cached}

    try:
        prov_dict = {
            "type": body.type,
            "base_url": body.base_url,
            "api_key": api_key,
            "model": "dummy",
            "params_json": json.dumps(body.params),
        }

        provider = provider_factory(prov_dict)
        models = await provider.fetch_models()

        # Filter and simplify for frontend
        simplified_models = []
        for m in models:
            if isinstance(m, dict) and "id" in m:
                simplified_models.append(
                    {
                        "id": m["id"],
                        "name": m.get("name", m["id"]),
                        "context_length": m.get("context_length", None),
                        "pricing": m.get("pricing", None),
                        "architecture": m.get("architecture", None),
                    }
                )

        # Sort alphabetically by name or ID
        simplified_models.sort(key=lambda x: x["name"].lower() if x["name"] else x["id"].lower())

        await _model_cache.set(cache_key, simplified_models)
        return {"data": simplified_models}

    except Exception as e:
        logger.exception("Failed to fetch models from standard provider")
        raise HTTPException(500, f"Failed to fetch models: {str(e)}")

@router.get("/openrouter/models")
async def get_openrouter_models():
    cached = await _or_cache.get("models")
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://openrouter.ai/api/v1/models")
            resp.raise_for_status()
            data = resp.json()
            await _or_cache.set("models", data)
            return data
    except Exception as e:
        logger.exception("Failed to fetch openrouter models")
        raise HTTPException(500, f"Failed to fetch models: {str(e)}")

@router.get("/openrouter/endpoints/{model:path}")
async def get_openrouter_endpoints(model: str):
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://openrouter.ai/api/v1/models/{model}/endpoints")
            if resp.status_code == 404:
                return {"data": {"endpoints": []}}
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.exception("Failed to fetch openrouter endpoints for model %s", model)
        raise HTTPException(500, f"Failed to fetch endpoints: {str(e)}")

class SecretUpdate(BaseModel):
    name: str
    value: str

@router.post("/secrets")
async def update_secret(body: SecretUpdate, db: aiosqlite.Connection = Depends(get_db)):
    if not body.value:
        await db.execute("DELETE FROM secrets WHERE name = ?", (body.name,))
    else:
        await db.execute(
            "INSERT INTO secrets (name, value) VALUES (?, ?) ON CONFLICT(name) DO UPDATE SET value = excluded.value",
            (body.name, body.value),
        )
    await db.commit()
    return {"ok": True}

@router.get("/secrets")
async def list_secrets(db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT name, value FROM secrets ORDER BY name") as cur:
        out = []
        for r in await cur.fetchall():
            val = r["value"]
            preview = f"{val[:4]}...{val[-4:]}" if len(val) > 8 else "***"
            out.append({"name": r["name"], "preview": preview})
        return {"data": out}

@router.delete("/secrets/{name}", status_code=204)
async def delete_secret(name: str, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM secrets WHERE name = ?", (name,))
    await db.commit()
    return {"ok": True}

async def get_openrouter_model_modalities(model_id: str) -> list[str] | None:
    """Look up input_modalities for an OpenRouter model from the in-memory cache.

    Fetches the full model list if the cache is cold or stale.
    Returns None if the model is not found or an error occurs.
    """

    async def _fetch():
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://openrouter.ai/api/v1/models",
                headers={},
                timeout=MODEL_FETCH_HTTP_TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()

    data = await _or_cache.get_or_refresh("models", _fetch)
    if not data:
        return None

    models = data.get("data") if isinstance(data, dict) else data
    if not isinstance(models, list):
        return None

    for m in models:
        if isinstance(m, dict) and m.get("id") == model_id:
            arch = m.get("architecture")
            if isinstance(arch, dict):
                return arch.get("input_modalities")

    return None
