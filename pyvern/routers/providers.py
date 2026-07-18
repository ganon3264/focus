from pydantic import BaseModel
import json
import uuid
from datetime import datetime, timezone

import aiosqlite
import httpx
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


_OPENROUTER_CACHE = None
_OPENROUTER_CACHE_TIME = 0


from pyvern.providers import create_provider

_MODELS_CACHE = {}
_MODELS_CACHE_TIME = {}

class FetchModelsRequest(BaseModel):
    type: str
    base_url: str | None = None
    api_key: str | None = None
    params: dict = {}

@router.post("/fetch_models")
async def fetch_models(body: FetchModelsRequest, db: aiosqlite.Connection = Depends(get_db)):
    global _MODELS_CACHE, _MODELS_CACHE_TIME
    import time
    now = time.time()
    
    # Resolve api key if it's a secret
    api_key = body.api_key or ""
    if api_key.startswith("SECRET:"):
        secret_name = api_key[7:]
        async with db.execute("SELECT value FROM secrets WHERE name = ?", (secret_name,)) as cur:
            secret_row = await cur.fetchone()
            if secret_row:
                api_key = secret_row["value"]
            else:
                api_key = ""
                
    # Cache key based on provider type and api key hash (to avoid caching across different keys)
    cache_key = f"{body.type}_{hash(api_key)}"
    if cache_key in _MODELS_CACHE and now - _MODELS_CACHE_TIME.get(cache_key, 0) < 300:
        return {"data": _MODELS_CACHE[cache_key]}

    try:
        # Create a dummy provider to get the properly constructed headers and base URL
        # We pass a dummy model name just to instantiate the class
        prov_dict = {
            "type": body.type,
            "base_url": body.base_url,
            "api_key": api_key,
            "model": "dummy",
            "params_json": json.dumps(body.params)
        }
        
        provider = create_provider(prov_dict)
        base_url = provider.base_url.rstrip("/")
        
        # If openrouter, use their specific public endpoint without auth
        if body.type == "openrouter":
            url = "https://openrouter.ai/api/v1/models"
            headers = {}
        else:
            url = f"{base_url}/models"
            headers = provider._extra_headers()
            if api_key and "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {api_key}"
                
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, timeout=10.0)
            resp.raise_for_status()
            data = resp.json()
            
            # Normalize response
            models = []
            if "data" in data and isinstance(data["data"], list):
                models = data["data"]
            elif isinstance(data, list):
                models = data
            else:
                # Attempt to extract anything that looks like a model ID
                models = []
                
            # Filter and simplify for frontend
            simplified_models = []
            for m in models:
                if isinstance(m, dict) and "id" in m:
                    simplified_models.append({
                        "id": m["id"],
                        "name": m.get("name", m["id"]),
                        "context_length": m.get("context_length", None),
                        "pricing": m.get("pricing", None)
                    })
            
            # Sort alphabetically by name or ID
            simplified_models.sort(key=lambda x: x["name"].lower() if x["name"] else x["id"].lower())
            
            _MODELS_CACHE[cache_key] = simplified_models
            _MODELS_CACHE_TIME[cache_key] = now
            return {"data": simplified_models}
            
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch models: {str(e)}")

@router.get("/openrouter/models")
async def get_openrouter_models():
    global _OPENROUTER_CACHE, _OPENROUTER_CACHE_TIME
    import time
    now = time.time()
    if _OPENROUTER_CACHE and now - _OPENROUTER_CACHE_TIME < 300:
        return _OPENROUTER_CACHE

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get("https://openrouter.ai/api/v1/models")
            resp.raise_for_status()
            data = resp.json()
            _OPENROUTER_CACHE = data
            _OPENROUTER_CACHE_TIME = now
            return data
    except Exception as e:
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
            (body.name, body.value)
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
