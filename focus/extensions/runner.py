from __future__ import annotations

import asyncio
import base64
import json
import logging
import subprocess
from typing import Any

import aiosqlite
from fastapi import HTTPException

import focus.crud as crud
from focus.core.macros import apply_macros, build_base_macros
from focus.core.message_render import render_message_segments
from focus.db import extensions as ext_db
from focus.db.chats import bind_attachments_to_message, create_attachment, edit_message_create_variant
from focus.extensions import ExtensionResult
from focus.extensions.loader import ExtensionSpec, _parse_command

logger = logging.getLogger("focus.extensions.runner")


def _subprocess_script(spec: ExtensionSpec, envelope: dict) -> tuple[str, str, int]:
    command = _parse_command(spec.command)
    try:
        proc = subprocess.run(
            command,
            input=json.dumps(envelope, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=spec.timeout,
        )
    except subprocess.TimeoutExpired:
        return "", f"extension timed out after {spec.timeout}s", 124
    return proc.stdout, proc.stderr, proc.returncode


async def run_extension(spec: ExtensionSpec, envelope: dict) -> ExtensionResult:
    stdout, stderr, rc = await asyncio.to_thread(_subprocess_script, spec, envelope)

    if rc != 0:
        err = stderr.strip() or f"exit code {rc}"
        return ExtensionResult(status="error", error=err)

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        # Non-JSON stdout is treated as plain text content (friendly for naive scripts).
        return ExtensionResult(status="done", content=stdout)

    if isinstance(data, dict) and data.get("error") and "status" not in data:
        data = {"status": "error", "error": data["error"], "logs": data.get("logs", [])}
    if not isinstance(data, dict):
        return ExtensionResult(status="error", error="extension must output a JSON object")

    try:
        return ExtensionResult.model_validate(data)
    except Exception as e:
        return ExtensionResult(status="error", error=f"invalid extension output: {e}")


async def build_envelope(
    db: aiosqlite.Connection,
    spec: ExtensionSpec,
    chat_id: str,
    message_id: str,
    config_overrides: dict | None = None,
) -> tuple[dict, dict, dict]:
    """Build the stdin envelope and return ``(envelope, target, chat)``.

    Resolves macros on ``target.content`` (so rewrite/TTS see natural text) while
    keeping ``raw_content`` as the stored value. ``segments`` stays the rendered
    (stored) segmentation so extensions can filter by ``text`` type.
    """
    async with db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)) as cur:
        chat_row = await cur.fetchone()
    if not chat_row:
        raise HTTPException(404, "Chat not found")
    chat = dict(chat_row)

    messages = await crud.get_chat_messages(db, chat_id)
    target = next((m for m in messages if m["id"] == message_id), None)
    if not target:
        raise HTTPException(404, "Message not found")

    char = await crud.get_character(db, chat.get("character_id"))
    persona = await crud.get_persona(db, chat.get("persona_id"))
    preset = await crud.get_preset(db, chat.get("preset_id"))

    char_card = (char or {}).get("card")
    raw_content = target.get("content", "")
    if char_card:
        content = apply_macros(raw_content, build_base_macros(char_card, persona))
    else:
        content = raw_content

    active_provider = await crud.get_active_provider(db)

    # Merge spec defaults → stored config → per-run overrides.
    stored_config = await ext_db.get_config(db, spec.name)
    config: dict[str, Any] = {p.name: p.default for p in spec.params}
    config.update(stored_config)
    if config_overrides:
        config.update({k: v for k, v in config_overrides.items() if k in config})

    secrets = await _collect_secrets(db, spec.secrets)

    target_out = {
        "message_id": target["id"],
        "variant_id": target.get("variant_id"),
        "role": target["role"],
        "position": target["position"],
        "content": content,
        "raw_content": raw_content,
        "segments": target.get("segments") or render_message_segments(content, target.get("variant_meta")),
        "reasoning": target.get("reasoning"),
        "attachments": target.get("attachments", []),
        "tool_calls": target.get("tool_calls", []),
        "model_name": target.get("model_name"),
        "created_at": target.get("created_at"),
    }

    envelope = {
        "extension": {"name": spec.name, "description": spec.description},
        "action": spec.name,
        "chat": {
            "id": chat_id,
            "character": (char or {}).get("name", ""),
            "persona": (persona or {}).get("name", ""),
            "preset": (preset or {}).get("name", ""),
            "provider": active_provider.get("provider_type", ""),
        },
        "target": target_out,
        "config": config,
        "secrets": secrets,
    }

    if "transcript" in spec.needs:
        envelope["transcript"] = [
            {"role": m["role"], "content": m.get("content", ""), "segments": m.get("segments")} for m in messages
        ]

    return envelope, target, chat


async def _collect_secrets(db: aiosqlite.Connection, names: list[str]) -> dict[str, str]:
    if not names:
        return {}
    placeholders = ",".join("?" * len(names))
    async with db.execute(f"SELECT name, value FROM secrets WHERE name IN ({placeholders})", names) as cur:
        rows = await cur.fetchall()
    return {row["name"]: row["value"] for row in rows}


async def apply_actions(
    db: aiosqlite.Connection,
    spec: ExtensionSpec,
    result: ExtensionResult,
    chat: dict,
    target: dict,
) -> dict:
    """Execute the requested side effects (files, create_swipe).

    Extensions are declarative and user-initiated: they request side effects and
    Focus performs them. There is no ``writes`` flag (it never captured a real
    boundary — the script is trusted and could write anyway), so a requested
    ``create_swipe`` is always honored.

    Returns the summary the API returns to the client.
    """
    logs: list[dict] = []
    for log in result.logs:
        logger.info("ext[%s] %s: %s", spec.name, log.level, log.message)
        logs.append({"level": log.level, "message": log.message})

    attachments_added = 0
    swipe_created = False
    new_variant: dict | None = None
    files_out: list[dict] = []

    for f in result.files:
        try:
            data = base64.b64decode(f.data)
        except Exception:
            logs.append({"level": "error", "message": f"invalid base64 in file {f.name}"})
            continue
        files_out.append({"name": f.name, "mime": f.mime, "data": f.data, "length": len(data)})
        if result.attach:
            att = await create_attachment(db, chat["id"], f.name, data, f.mime)
            await bind_attachments_to_message(db, chat["id"], target["id"], target.get("variant_id"), [att["id"]])
            attachments_added += 1
    if attachments_added:
        logs.append({"level": "success", "message": f"attached {attachments_added} file(s)"})

    action = result.action
    if action and action.type == "create_swipe":
        content = action.content if action.content is not None else (result.content or "")
        message_id = action.message_id or target["id"]
        res = await edit_message_create_variant(
            db,
            chat["id"],
            message_id,
            content,
            action.reasoning,
            None,
            action.segments,
        )
        swipe_created = True
        new_variant = res

    if result.content and not swipe_created and not result.files:
        logs.append({"level": "info", "message": result.content})

    return {
        "status": "error" if result.status == "error" else "done",
        "error": result.error,
        "message_id": target["id"],
        "variant_index": new_variant.get("variant_index") if new_variant else None,
        "variant_id": new_variant.get("variant_id") if new_variant else None,
        "swipe_created": swipe_created,
        "attachments_added": attachments_added,
        "content": result.content,
        "logs": logs,
        "files": files_out,
    }
