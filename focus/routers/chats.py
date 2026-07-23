from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

import focus.crud as crud
import focus.db as db
from focus.core.database import get_db
from focus.core.models import ChatCreate, MessageEdit
from focus.core.paths import ATTACHMENTS_DIR
from focus.core.utils import read_upload

router = APIRouter()


@router.post("/", status_code=201)
async def create_chat(body: ChatCreate, _db=Depends(get_db)):
    char_id = body.character_id if body.character_id else None
    pers_id = body.persona_id if body.persona_id else None
    pres_id = body.preset_id if body.preset_id else None

    chat_id = await db.create_chat(_db, char_id, pers_id, pres_id, body.title or "New Chat")

    if body.character_id:
        await db.create_greeting_messages(_db, chat_id, body.character_id)

    await _db.commit()
    return {"id": chat_id}


@router.get("/")
async def list_chats(_db=Depends(get_db)):
    query = """
        SELECT c.*,
               (SELECT mv.content
                FROM messages m
                JOIN message_variants mv ON m.id = mv.message_id AND m.active_index = mv.variant_index
                WHERE m.chat_id = c.id
                ORDER BY m.position DESC LIMIT 1) as last_message
        FROM chats c WHERE c.is_deleted = 0 ORDER BY c.updated_at DESC
    """
    async with _db.execute(query) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/trash")
async def list_trashed_chats(_db=Depends(get_db)):
    query = """
        SELECT c.*,
               ch.name as character_name,
               ch.image_path as character_image,
               p.name as persona_name,
               (SELECT mv.content
                FROM messages m
                JOIN message_variants mv ON m.id = mv.message_id AND m.active_index = mv.variant_index
                WHERE m.chat_id = c.id
                ORDER BY m.position DESC LIMIT 1) as last_message
        FROM chats c
        LEFT JOIN characters ch ON ch.id = c.character_id
        LEFT JOIN personas p ON p.id = c.persona_id
        WHERE c.is_deleted = 1 ORDER BY c.updated_at DESC
    """
    async with _db.execute(query) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/{chat_id}")
async def get_chat(chat_id: str, _db=Depends(get_db)):
    async with _db.execute("SELECT * FROM chats WHERE id = ? AND is_deleted = 0", (chat_id,)) as cur:
        chat = await cur.fetchone()
    if not chat:
        raise HTTPException(404, "Chat not found")

    messages = await crud.fetch_active_variants(_db, chat_id, extra_cols="m.created_at")

    async with _db.execute(
        "SELECT tool_name, enabled FROM chat_tool_states WHERE chat_id = ?", (chat_id,)
    ) as cur:
        tool_states = {row["tool_name"]: bool(row["enabled"]) for row in await cur.fetchall()}

    result = dict(chat)
    result["messages"] = messages
    result["tool_states"] = tool_states
    return result


@router.patch("/{chat_id}")
async def update_chat(chat_id: str, body: dict, _db=Depends(get_db)):
    await db.update_chat(_db, chat_id, body)
    await _db.commit()
    return {"ok": True}


@router.put("/{chat_id}/tool-states")
async def update_chat_tool_states(chat_id: str, body: dict[str, bool], _db=Depends(get_db)):
    await db.update_chat_tool_states(_db, chat_id, body)
    await _db.commit()
    return {"ok": True}


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: str,
    hard: bool = False,
    _db=Depends(get_db),
):
    if hard:
        await db.hard_delete_chat(_db, chat_id)
    else:
        await db.delete_chat(_db, chat_id)
    await _db.commit()


@router.post("/{chat_id}/restore", status_code=200)
async def restore_chat(chat_id: str, _db=Depends(get_db)):
    async with _db.execute("SELECT id FROM chats WHERE id = ?", (chat_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Chat not found")
    await db.restore_chat(_db, chat_id)
    await _db.commit()
    return {"ok": True}


@router.get("/{chat_id}/messages/{message_id}")
async def get_message(chat_id: str, message_id: str, _db=Depends(get_db)):
    async with _db.execute(
        """SELECT mv.content, mv.reasoning, mv.id as variant_id
           FROM messages m
           JOIN message_variants mv ON mv.message_id = m.id AND mv.variant_index = m.active_index
           WHERE m.id = ? AND m.chat_id = ?""",
        (message_id, chat_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Message not found")

    async with _db.execute(
        "SELECT * FROM message_attachments WHERE variant_id = ? ORDER BY created_at",
        (row["variant_id"],),
    ) as cur:
        attachments = [dict(r) for r in await cur.fetchall()]

    async with _db.execute(
        "SELECT * FROM tool_calls WHERE variant_id = ? ORDER BY created_at",
        (row["variant_id"],),
    ) as cur:
        tool_calls_rows = await cur.fetchall()

    tool_calls = []
    for tc in tool_calls_rows:
        tool_calls.append({
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["tool_name"],
                "arguments": tc["arguments"],
            },
            "result": tc["result"],
            "is_error": bool(tc["is_error"]),
            "image_data": crud.extract_image_from_extra(tc.get("extra_message_json")),
        })

    return {"content": row["content"], "reasoning": row["reasoning"], "attachments": attachments, "tool_calls": tool_calls}


@router.delete("/{chat_id}/messages/{message_id}", status_code=204)
async def delete_message(
    chat_id: str,
    message_id: str,
    _db=Depends(get_db),
):
    """Delete a message and all messages after it (for retry/truncation)."""
    await db.delete_message_and_after(_db, chat_id, message_id)
    await _db.commit()


class BulkDeleteRequest(BaseModel):
    message_ids: list[str]


@router.post("/{chat_id}/messages/bulk_delete")
async def bulk_delete_messages(
    chat_id: str,
    body: BulkDeleteRequest,
    _db=Depends(get_db),
):
    if not body.message_ids:
        return {"deleted": 0}

    count = await db.bulk_delete_messages(_db, chat_id, body.message_ids)
    await _db.commit()
    return {"deleted": count}


@router.patch("/{chat_id}/messages/{message_id}")
async def edit_message(
    chat_id: str,
    message_id: str,
    body: MessageEdit,
    _db=Depends(get_db),
):
    """
    Edit a message. Creates a new variant and sets it as active.
    Previous variants are preserved (swipeable).
    """
    result = await db.edit_message_create_variant(
        _db, chat_id, message_id, body.content, body.reasoning, body.attachment_ids,
    )
    await _db.commit()
    return {"ok": True, **result}


@router.post("/{chat_id}/messages/{message_id}/swipe")
async def swipe_message(
    chat_id: str,
    message_id: str,
    direction: str = Form("next"),
    _db=Depends(get_db),
):
    """
    Navigate between existing variants.
    Returns needs_generation=True when swiping past the last variant,
    so the client knows to fire a /stream request.
    """
    result = await db.swipe_message(_db, chat_id, message_id, direction)
    await _db.commit()
    return {"ok": True, **result}


@router.post("/{chat_id}/messages/{message_id}/branch")
async def branch_chat(
    chat_id: str,
    message_id: str,
    _db=Depends(get_db),
):
    new_chat_id = await db.branch_chat(_db, chat_id, message_id)
    await _db.commit()
    return {"id": new_chat_id}


@router.post("/{chat_id}/attachments", status_code=201)
async def upload_attachments(
    chat_id: str,
    files: list[UploadFile] = File(...),
    _db=Depends(get_db),
):
    async with _db.execute("SELECT id FROM chats WHERE id = ?", (chat_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Chat not found")

    ATTACHMENTS_DIR.mkdir(exist_ok=True)

    results = []
    for file in files:
        entry = await db.create_attachment(
            _db, chat_id, file.filename, await read_upload(file), file.content_type,
        )
        results.append(entry)

    await _db.commit()
    return {"attachments": results}


@router.delete("/{chat_id}/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    chat_id: str,
    attachment_id: str,
    _db=Depends(get_db),
):
    await db.delete_attachment(_db, chat_id, attachment_id)
    await _db.commit()
