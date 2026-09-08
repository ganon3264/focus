from __future__ import annotations

import base64
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


class TestRequest(BaseModel):
    config: dict[str, Any] | None = None
    text: str | None = None


_DEFAULT_TEST_TEXT = "Hello from the audio.cpp TTS test."


async def _collect_secrets(db: Connection, names: list[str]) -> dict[str, str]:
    if not names:
        return {}
    placeholders = ",".join("?" * len(names))
    async with db.execute(f"SELECT name, value FROM secrets WHERE name IN ({placeholders})", names) as cur:
        rows = await cur.fetchall()
    return {row["name"]: row["value"] for row in rows}


@router.post("/extensions/{name}/test")
async def test_extension(name: str, body: TestRequest, db: Connection = Depends(get_db)):
    """Run an extension against a synthetic sample message.

    This is the "Test" button in the extensions modal: it builds a small
    assistant-text envelope, runs the script, and reports status/logs along with
    any returned ``files`` (so the frontend can play generated audio). It never
    calls ``apply_actions`` — no swipes or attachments are written.
    """
    spec = find_extension(name)
    if spec is None:
        raise HTTPException(404, "Extension not found")

    text = (body.text or "").strip() or _DEFAULT_TEST_TEXT

    # Same resolve order as build_envelope: spec defaults → stored config → per-run.
    config: dict[str, Any] = {p.name: p.default for p in spec.params}
    config.update(await ext_db.get_config(db, name))
    if body.config:
        config.update({k: v for k, v in body.config.items() if k in config})

    secrets = await _collect_secrets(db, spec.secrets)

    envelope = {
        "extension": {"name": spec.name, "description": spec.description},
        "action": spec.name,
        "chat": {
            "id": None,
            "character": "(test)",
            "persona": "(test)",
            "preset": "(test)",
            "provider": "",
        },
        "target": {
            "message_id": None,
            "variant_id": None,
            "role": "assistant",
            "position": 0,
            "content": text,
            "raw_content": text,
            "segments": [{"type": "text", "content": text}],
            "reasoning": None,
            "attachments": [],
            "tool_calls": [],
            "model_name": "test",
        },
        "config": config,
        "secrets": secrets,
    }

    result = await run_extension(spec, envelope)
    files = []
    for f in result.files:
        try:
            length = len(base64.b64decode(f.data))
        except Exception:
            length = 0
        files.append({"name": f.name, "mime": f.mime, "data": f.data, "length": length})

    return {
        "status": result.status,
        "error": result.error,
        "content": result.content,
        "action": result.action.type if result.action else None,
        "logs": [log.model_dump() for log in result.logs],
        "files": files,
    }


@router.post("/extensions/{name}/run")
async def run_ext(name: str, body: RunRequest, db: Connection = Depends(get_db)):
    spec = find_extension(name)
    if spec is None:
        raise HTTPException(404, "Extension not found")

    envelope, target, chat = await build_envelope(
        db,
        spec,
        body.chat_id,
        body.message_id,
        config_overrides=body.config,
    )
    result = await run_extension(spec, envelope)
    summary = await apply_actions(db, spec, result, chat, target)
    await db.commit()
    return summary
