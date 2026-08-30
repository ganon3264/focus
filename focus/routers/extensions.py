from __future__ import annotations

from typing import Any

from aiosqlite import Connection
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

import focus.db.extensions as ext_db
from focus.core.database import get_db
from focus.extensions.loader import find_extension, get_all_extensions, reload_extensions
from focus.extensions.runner import apply_actions, build_envelope, run_extension

router = APIRouter()


def _serialize_spec(spec) -> dict:
    return {
        "name": spec.name,
        "description": spec.description,
        "category": spec.category,
        "icon": spec.icon,
        "roles": spec.roles,
        "needs": spec.needs,
        "triggers": spec.triggers,
        "secrets": spec.secrets,
        "params": [
            {
                "name": p.name,
                "type": p.type,
                "description": p.description,
                "default": p.default,
                "enum": p.enum,
                "required": p.required,
            }
            for p in spec.params
        ],
    }


@router.get("/extensions")
async def list_extensions():
    return [_serialize_spec(spec) for spec in get_all_extensions()]


@router.post("/extensions/reload")
async def reload_extensions_endpoint():
    count = len(reload_extensions())
    return {"ok": True, "count": count}


@router.get("/extensions/config")
async def list_configs(db: Connection = Depends(get_db)):
    return await ext_db.get_configs(db)


@router.put("/extensions/{name}/config")
async def save_config(name: str, body: dict[str, Any], db: Connection = Depends(get_db)):
    if find_extension(name) is None:
        raise HTTPException(404, "Extension not found")
    await ext_db.set_config(db, name, body)
    await db.commit()
    return {"ok": True}


@router.get("/chats/{chat_id}/extensions")
async def get_chat_extensions(chat_id: str, db: Connection = Depends(get_db)):
    states = await ext_db.get_chat_states(db, chat_id)
    return {"states": states}


class ChatExtensionStates(BaseModel):
    states: dict[str, bool]


@router.put("/chats/{chat_id}/extensions")
async def set_chat_extensions(chat_id: str, body: ChatExtensionStates, db: Connection = Depends(get_db)):
    await ext_db.set_chat_states(db, chat_id, body.states)
    await db.commit()
    return {"ok": True}


class RunRequest(BaseModel):
    chat_id: str
    message_id: str
    config: dict[str, Any] | None = None


@router.post("/extensions/{name}/run")
async def run_ext(name: str, body: RunRequest, db: Connection = Depends(get_db)):
    spec = find_extension(name)
    if spec is None:
        raise HTTPException(404, "Extension not found")

    envelope, target, chat = await build_envelope(
        db, spec, body.chat_id, body.message_id, config_overrides=body.config,
    )
    result = await run_extension(spec, envelope)
    summary = await apply_actions(db, spec, result, chat, target)
    await db.commit()
    return summary
