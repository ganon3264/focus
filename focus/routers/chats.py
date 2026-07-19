import uuid
from pathlib import Path

import aiosqlite
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

import focus.crud as crud
from focus.core.card_parser import safe_load_card
from focus.core.database import get_db
from focus.core.models import ChatCreate, MessageEdit
from focus.core.paths import ATTACHMENTS_DIR
from focus.core.utils import now_iso, read_upload

router = APIRouter()


@router.post("/", status_code=201)
async def create_chat(body: ChatCreate, db: aiosqlite.Connection = Depends(get_db)):
    chat_id = str(uuid.uuid4())
    now = now_iso()

    char_id = body.character_id if body.character_id else None
    pers_id = body.persona_id if body.persona_id else None
    pres_id = body.preset_id if body.preset_id else None

    try:
        await db.execute(
            "INSERT INTO chats (id, title, character_id, persona_id, preset_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chat_id, body.title or "New Chat", char_id, pers_id, pres_id, now, now),
        )
    except aiosqlite.IntegrityError as e:
        raise HTTPException(400, f"Invalid reference: {e}")

    if body.character_id:
        async with db.execute("SELECT card_json FROM characters WHERE id = ?", (body.character_id,)) as cur:
            row = await cur.fetchone()
        if row:
            card = safe_load_card(row) or {"first_mes": "", "alternate_greetings": []}
            greetings = []
            if card["first_mes"]:
                greetings.append(card["first_mes"])
            greetings.extend(card["alternate_greetings"])

            if greetings:
                msg_id = str(uuid.uuid4())
                await db.execute(
                    "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (msg_id, chat_id, "assistant", 0, 0, now),
                )
                for i, text in enumerate(greetings):
                    await db.execute(
                        "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                        (str(uuid.uuid4()), msg_id, i, text, now),
                    )

    await db.commit()
    return {"id": chat_id}


@router.get("/")
async def list_chats(db: aiosqlite.Connection = Depends(get_db)):
    query = """
        SELECT c.*,
               (SELECT mv.content
                FROM messages m
                JOIN message_variants mv ON m.id = mv.message_id AND m.active_index = mv.variant_index
                WHERE m.chat_id = c.id
                ORDER BY m.position DESC LIMIT 1) as last_message
        FROM chats c WHERE c.is_deleted = 0 ORDER BY c.updated_at DESC
    """
    async with db.execute(query) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/trash")
async def list_trashed_chats(db: aiosqlite.Connection = Depends(get_db)):
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
    async with db.execute(query) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/{chat_id}")
async def get_chat(chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM chats WHERE id = ? AND is_deleted = 0", (chat_id,)) as cur:
        chat = await cur.fetchone()
    if not chat:
        raise HTTPException(404, "Chat not found")

    messages = await crud.fetch_active_variants(db, chat_id, extra_cols="m.created_at")

    result = dict(chat)
    result["messages"] = messages
    return result


@router.patch("/{chat_id}")
async def update_chat(chat_id: str, body: dict, db: aiosqlite.Connection = Depends(get_db)):
    allowed = {"title", "preset_id", "character_id", "persona_id", "tool_calls_enabled", "tool_read_only"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if updates:
        cols = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [now_iso(), chat_id]
        try:
            await db.execute(f"UPDATE chats SET {cols}, updated_at = ? WHERE id = ?", vals)
            await db.commit()
        except aiosqlite.IntegrityError as e:
            raise HTTPException(400, f"Invalid reference: {e}")
    return {"ok": True}


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    chat_id: str,
    hard: bool = False,
    db: aiosqlite.Connection = Depends(get_db),
):
    if hard:
        await db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    else:
        await db.execute("UPDATE chats SET is_deleted = 1 WHERE id = ?", (chat_id,))
    await db.commit()


@router.post("/{chat_id}/restore", status_code=200)
async def restore_chat(chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT id FROM chats WHERE id = ?", (chat_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Chat not found")
    await db.execute("UPDATE chats SET is_deleted = 0 WHERE id = ?", (chat_id,))
    await db.commit()
    return {"ok": True}


@router.get("/{chat_id}/messages/{message_id}")
async def get_message(chat_id: str, message_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        """SELECT mv.content, mv.reasoning, mv.id as variant_id
           FROM messages m
           JOIN message_variants mv ON mv.message_id = m.id AND mv.variant_index = m.active_index
           WHERE m.id = ? AND m.chat_id = ?""",
        (message_id, chat_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Message not found")

    async with db.execute(
        "SELECT * FROM message_attachments WHERE variant_id = ? ORDER BY created_at",
        (row["variant_id"],),
    ) as cur:
        attachments = [dict(r) for r in await cur.fetchall()]

    async with db.execute(
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
        })

    return {"content": row["content"], "reasoning": row["reasoning"], "attachments": attachments, "tool_calls": tool_calls}


@router.delete("/{chat_id}/messages/{message_id}", status_code=204)
async def delete_message(
    chat_id: str,
    message_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Delete a message and all messages after it (for retry/truncation)."""
    async with db.execute("SELECT position FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Message not found")

    await db.execute("DELETE FROM messages WHERE chat_id = ? AND position >= ?", (chat_id, row["position"]))
    await db.commit()


class BulkDeleteRequest(BaseModel):
    message_ids: list[str]


@router.post("/{chat_id}/messages/bulk_delete")
async def bulk_delete_messages(
    chat_id: str,
    body: BulkDeleteRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    if not body.message_ids:
        return {"deleted": 0}

    placeholders = ",".join("?" * len(body.message_ids))
    await db.execute(
        f"DELETE FROM messages WHERE chat_id = ? AND id IN ({placeholders})",
        [chat_id] + body.message_ids,
    )
    await db.commit()
    return {"deleted": len(body.message_ids)}


@router.patch("/{chat_id}/messages/{message_id}")
async def edit_message(
    chat_id: str,
    message_id: str,
    body: MessageEdit,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Edit a message. Creates a new variant and sets it as active.
    Previous variants are preserved (swipeable).
    """
    async with db.execute(
        "SELECT active_index FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Message not found")

    async with db.execute(
        "SELECT mv.model_name FROM message_variants mv JOIN messages m ON m.active_index = mv.variant_index WHERE mv.message_id = ? AND m.id = ?",
        (message_id, message_id),
    ) as cur:
        prev = await cur.fetchone()
    prev_model = prev["model_name"] if prev else None

    async with db.execute("SELECT MAX(variant_index) FROM message_variants WHERE message_id = ?", (message_id,)) as cur:
        max_row = await cur.fetchone()

    new_index = (max_row[0] or 0) + 1
    now = now_iso()
    new_variant_id = str(uuid.uuid4())

    from focus.core.message_render import render_message_segments
    import json
    _segments = render_message_segments(body.content, body.reasoning)
    _segments_json = json.dumps(_segments) if _segments else None

    await db.execute(
        "INSERT INTO message_variants (id, message_id, variant_index, content, created_at, model_name, reasoning, segments_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (new_variant_id, message_id, new_index, body.content, now, prev_model, body.reasoning, _segments_json),
    )

    for att_id in body.attachment_ids:
        async with db.execute("SELECT * FROM message_attachments WHERE id = ?", (att_id,)) as cur:
            att = await cur.fetchone()
        if att:
            if att["variant_id"] is None:
                await db.execute(
                    "UPDATE message_attachments SET message_id = ?, variant_id = ? WHERE id = ?",
                    (message_id, new_variant_id, att["id"]),
                )
            else:
                await db.execute(
                    "INSERT INTO message_attachments (id, chat_id, message_id, variant_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()),
                        chat_id,
                        message_id,
                        new_variant_id,
                        att["file_path"],
                        att["mime_type"],
                        now_iso(),
                    ),
                )

    await db.execute("UPDATE messages SET active_index = ? WHERE id = ?", (new_index, message_id))
    await db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
    await db.commit()
    return {"ok": True, "variant_index": new_index, "variant_id": new_variant_id}


@router.post("/{chat_id}/messages/{message_id}/swipe")
async def swipe_message(
    chat_id: str,
    message_id: str,
    direction: str = Form("next"),
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Navigate between existing variants.
    Returns needs_generation=True when swiping past the last variant,
    so the client knows to fire a /stream request.
    """
    async with db.execute(
        "SELECT active_index, position FROM messages WHERE id = ? AND chat_id = ?",
        (message_id, chat_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Message not found")

    current = row["active_index"]
    is_greeting = row["position"] == 0

    async with db.execute("SELECT MAX(variant_index) FROM message_variants WHERE message_id = ?", (message_id,)) as cur:
        max_row = await cur.fetchone()
    max_index = max_row[0] or 0

    if direction == "prev":
        new_index = max(0, current - 1)
    else:
        if current >= max_index:
            if is_greeting:
                # Greeting swipe wraps around instead of triggering generation
                new_index = 0
            else:
                return {"needs_generation": True, "next_variant_index": current + 1}
        else:
            new_index = current + 1

    await db.execute("UPDATE messages SET active_index = ? WHERE id = ?", (new_index, message_id))
    await db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now_iso(), chat_id))
    await db.commit()

    async with db.execute(
        "SELECT content FROM message_variants WHERE message_id = ? AND variant_index = ?",
        (message_id, new_index),
    ) as cur:
        variant = await cur.fetchone()

    return {
        "ok": True,
        "variant_index": new_index,
        "content": variant["content"] if variant else "",
        "is_last": new_index == max_index,
    }


@router.post("/{chat_id}/messages/{message_id}/branch")
async def branch_chat(
    chat_id: str,
    message_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT character_id, persona_id, preset_id, title FROM chats WHERE id = ?", (chat_id,)
    ) as cur:
        chat = await cur.fetchone()
    if not chat:
        raise HTTPException(404, "Chat not found")

    async with db.execute("SELECT position FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Message not found")

    new_chat_id = str(uuid.uuid4())
    now = now_iso()

    await db.execute(
        "INSERT INTO chats (id, title, character_id, persona_id, preset_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            new_chat_id,
            f"Copy of {chat['title']}",
            chat["character_id"],
            chat["persona_id"],
            chat["preset_id"],
            now,
            now,
        ),
    )

    async with db.execute(
        "SELECT * FROM messages WHERE chat_id = ? AND position <= ? ORDER BY position",
        (chat_id, row["position"]),
    ) as cur:
        messages = [dict(r) for r in await cur.fetchall()]

    msg_id_map = {}
    for msg in messages:
        new_msg_id = str(uuid.uuid4())
        msg_id_map[msg["id"]] = new_msg_id
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (new_msg_id, new_chat_id, msg["role"], msg["position"], msg["active_index"], msg["created_at"]),
        )

        async with db.execute("SELECT * FROM message_variants WHERE message_id = ?", (msg["id"],)) as cur2:
            variants = [dict(r) for r in await cur2.fetchall()]
        for v in variants:
            new_variant_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at, model_name, reasoning, segments_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (new_variant_id, new_msg_id, v["variant_index"], v["content"], v["created_at"], v.get("model_name"), v.get("reasoning"), v.get("segments_json")),
            )
            async with db.execute("SELECT * FROM message_attachments WHERE variant_id = ?", (v["id"],)) as cur3:
                attachments = [dict(r) for r in await cur3.fetchall()]
            for att in attachments:
                await db.execute(
                    "INSERT INTO message_attachments (id, chat_id, message_id, variant_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()),
                        new_chat_id,
                        new_msg_id,
                        new_variant_id,
                        att["file_path"],
                        att["mime_type"],
                        att["created_at"],
                    ),
                )

            async with db.execute("SELECT * FROM tool_calls WHERE variant_id = ?", (v["id"],)) as cur4:
                old_tool_calls = [dict(r) for r in await cur4.fetchall()]
            for tc in old_tool_calls:
                await db.execute(
                    "INSERT INTO tool_calls (id, chat_id, message_id, variant_id, tool_name, arguments, result, is_error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(uuid.uuid4()),
                        new_chat_id,
                        new_msg_id,
                        new_variant_id,
                        tc["tool_name"],
                        tc["arguments"],
                        tc["result"],
                        tc["is_error"],
                        tc["created_at"],
                    ),
                )

    await db.commit()
    return {"id": new_chat_id}


@router.post("/{chat_id}/attachments", status_code=201)
async def upload_attachments(
    chat_id: str,
    files: list[UploadFile] = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute("SELECT id FROM chats WHERE id = ?", (chat_id,)) as cur:
        if not await cur.fetchone():
            raise HTTPException(404, "Chat not found")

    ATTACHMENTS_DIR.mkdir(exist_ok=True)

    results = []
    for file in files:
        attachment_id = str(uuid.uuid4())
        suffix = Path(file.filename).suffix.lower()
        if not suffix:
            suffix = ".bin"

        mime = file.content_type or "application/octet-stream"
        file_path = str(ATTACHMENTS_DIR / f"{attachment_id}{suffix}")

        content = await read_upload(file)
        try:
            Path(file_path).write_bytes(content)
        except OSError as e:
            raise HTTPException(500, f"Failed to save attachment {file.filename}: {e}")

        await db.execute(
            "INSERT INTO message_attachments (id, chat_id, message_id, variant_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (attachment_id, chat_id, None, None, file_path, mime, now_iso()),
        )
        results.append(
            {
                "id": attachment_id,
                "file_path": file_path,
                "mime_type": mime,
                "filename": file.filename,
            }
        )

    await db.commit()
    return {"attachments": results}


@router.delete("/{chat_id}/attachments/{attachment_id}", status_code=204)
async def delete_attachment(
    chat_id: str,
    attachment_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    async with db.execute(
        "SELECT file_path FROM message_attachments WHERE id = ? AND chat_id = ?",
        (attachment_id, chat_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Attachment not found")

    file_path = row["file_path"]
    await db.execute("DELETE FROM message_attachments WHERE id = ?", (attachment_id,))

    # Check if any other attachments share this file path (e.g. from variant duplication)
    async with db.execute("SELECT COUNT(*) FROM message_attachments WHERE file_path = ?", (file_path,)) as cur:
        count = (await cur.fetchone())[0]

    if count == 0:
        Path(file_path).unlink(missing_ok=True)

    await db.commit()
