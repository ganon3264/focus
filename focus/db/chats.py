from __future__ import annotations

import json
import uuid
from pathlib import Path

import aiosqlite

from focus.core.card_parser import safe_load_card
from focus.core.message_render import render_message_segments
from focus.core.paths import ATTACHMENTS_DIR
from focus.core.utils import now_iso
from focus.db._core import _db_conn


async def create_chat(
    db: aiosqlite.Connection,
    character_id: str | None = None,
    persona_id: str | None = None,
    preset_id: str | None = None,
    title: str = "New Chat",
) -> str:
    chat_id = str(uuid.uuid4())
    now = now_iso()
    try:
        await db.execute(
            "INSERT INTO chats (id, title, character_id, persona_id, preset_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (chat_id, title, character_id, persona_id, preset_id, now, now),
        )
    except aiosqlite.IntegrityError as e:
        from fastapi import HTTPException
        raise HTTPException(400, f"Invalid reference: {e}")
    return chat_id


async def create_greeting_messages(
    db: aiosqlite.Connection, chat_id: str, character_id: str
) -> None:
    async with db.execute("SELECT card_json FROM characters WHERE id = ?", (character_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return
    card = safe_load_card(row) or {"first_mes": "", "alternate_greetings": []}
    greetings = []
    if card["first_mes"]:
        greetings.append(card["first_mes"])
    greetings.extend(card["alternate_greetings"])
    if not greetings:
        return

    now = now_iso()
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


async def update_chat(db: aiosqlite.Connection, chat_id: str, updates: dict) -> None:
    allowed = {"title", "preset_id", "character_id", "persona_id", "tool_calls_enabled", "tool_read_only"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    if not updates:
        return
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [now_iso(), chat_id]
    try:
        await db.execute(f"UPDATE chats SET {cols}, updated_at = ? WHERE id = ?", vals)
    except aiosqlite.IntegrityError as e:
        from fastapi import HTTPException
        raise HTTPException(400, f"Invalid reference: {e}")


async def update_chat_tool_states(db: aiosqlite.Connection, chat_id: str, states: dict[str, bool]) -> None:
    for tool_name, enabled in states.items():
        await db.execute(
            "INSERT INTO chat_tool_states (chat_id, tool_name, enabled) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id, tool_name) DO UPDATE SET enabled = excluded.enabled",
            (chat_id, tool_name, enabled),
        )


async def delete_chat(db: aiosqlite.Connection, chat_id: str) -> None:
    await db.execute("UPDATE chats SET is_deleted = 1 WHERE id = ?", (chat_id,))


async def hard_delete_chat(db: aiosqlite.Connection, chat_id: str) -> None:
    await db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))


async def restore_chat(db: aiosqlite.Connection, chat_id: str) -> None:
    await db.execute("UPDATE chats SET is_deleted = 0 WHERE id = ?", (chat_id,))


async def create_message(
    db: aiosqlite.Connection,
    chat_id: str,
    role: str,
    position: int | None = None,
) -> str:
    msg_id = str(uuid.uuid4())
    now = now_iso()
    if position is None:
        async with db.execute("SELECT MAX(position) FROM messages WHERE chat_id = ?", (chat_id,)) as cur:
            pos_row = await cur.fetchone()
        position = (pos_row[0] if pos_row[0] is not None else -1) + 1
    await db.execute(
        "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (msg_id, chat_id, role, position, 0, now),
    )
    return msg_id


async def create_message_with_variant(
    db: aiosqlite.Connection,
    chat_id: str,
    role: str,
    content: str,
    variant_index: int = 0,
    position: int | None = None,
) -> tuple[str, str]:
    msg_id = await create_message(db, chat_id, role, position)
    variant_id = str(uuid.uuid4())
    now = now_iso()
    await db.execute(
        "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (variant_id, msg_id, variant_index, content, now),
    )
    await db.execute("UPDATE messages SET active_index = ? WHERE id = ?", (variant_index, msg_id))
    return msg_id, variant_id


async def delete_message_and_after(db: aiosqlite.Connection, chat_id: str, message_id: str) -> None:
    async with db.execute("SELECT position FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)) as cur:
        row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Message not found")
    await db.execute("DELETE FROM messages WHERE chat_id = ? AND position >= ?", (chat_id, row["position"]))


async def bulk_delete_messages(db: aiosqlite.Connection, chat_id: str, message_ids: list[str]) -> int:
    if not message_ids:
        return 0
    placeholders = ",".join("?" * len(message_ids))
    await db.execute(
        f"DELETE FROM messages WHERE chat_id = ? AND id IN ({placeholders})",
        [chat_id] + message_ids,
    )
    return len(message_ids)


async def edit_message_create_variant(
    db: aiosqlite.Connection,
    chat_id: str,
    message_id: str,
    content: str,
    reasoning: str | None = None,
    attachment_ids: list[str] | None = None,
) -> dict:
    async with db.execute(
        "SELECT active_index FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException
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

    _segments = render_message_segments(content, reasoning)
    _segments_json = json.dumps(_segments) if _segments else None

    await db.execute(
        "INSERT INTO message_variants (id, message_id, variant_index, content, created_at, model_name, reasoning, segments_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (new_variant_id, message_id, new_index, content, now, prev_model, reasoning, _segments_json),
    )

    for att_id in (attachment_ids or []):
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
                    (str(uuid.uuid4()), chat_id, message_id, new_variant_id, att["file_path"], att["mime_type"], now_iso()),
                )

    await db.execute("UPDATE messages SET active_index = ? WHERE id = ?", (new_index, message_id))
    await db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id))
    return {"variant_index": new_index, "variant_id": new_variant_id}


async def swipe_message(
    db: aiosqlite.Connection, chat_id: str, message_id: str, direction: str = "next"
) -> dict:
    async with db.execute(
        "SELECT active_index, position FROM messages WHERE id = ? AND chat_id = ?",
        (message_id, chat_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException
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
                new_index = 0
            else:
                return {"needs_generation": True, "next_variant_index": current + 1}
        else:
            new_index = current + 1

    await db.execute("UPDATE messages SET active_index = ? WHERE id = ?", (new_index, message_id))
    await db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now_iso(), chat_id))

    async with db.execute(
        "SELECT content FROM message_variants WHERE message_id = ? AND variant_index = ?",
        (message_id, new_index),
    ) as cur:
        variant = await cur.fetchone()

    return {
        "variant_index": new_index,
        "content": variant["content"] if variant else "",
        "is_last": new_index == max_index,
    }


async def branch_chat(db: aiosqlite.Connection, chat_id: str, message_id: str) -> str:
    async with db.execute(
        "SELECT character_id, persona_id, preset_id, title FROM chats WHERE id = ?", (chat_id,)
    ) as cur:
        chat = await cur.fetchone()
    if not chat:
        from fastapi import HTTPException
        raise HTTPException(404, "Chat not found")

    async with db.execute("SELECT position FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)) as cur:
        row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Message not found")

    new_chat_id = str(uuid.uuid4())
    now = now_iso()
    await db.execute(
        "INSERT INTO chats (id, title, character_id, persona_id, preset_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (new_chat_id, f"Copy of {chat['title']}", chat["character_id"], chat["persona_id"],
         chat["preset_id"], now, now),
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
                (new_variant_id, new_msg_id, v["variant_index"], v["content"], v["created_at"],
                 v.get("model_name"), v.get("reasoning"), v.get("segments_json")),
            )
            async with db.execute("SELECT * FROM message_attachments WHERE variant_id = ?", (v["id"],)) as cur3:
                attachments = [dict(r) for r in await cur3.fetchall()]
            for att in attachments:
                await db.execute(
                    "INSERT INTO message_attachments (id, chat_id, message_id, variant_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), new_chat_id, new_msg_id, new_variant_id, att["file_path"], att["mime_type"], att["created_at"]),
                )

            async with db.execute("SELECT * FROM tool_calls WHERE variant_id = ?", (v["id"],)) as cur4:
                old_tool_calls = [dict(r) for r in await cur4.fetchall()]
            for tc in old_tool_calls:
                await db.execute(
                    "INSERT INTO tool_calls (id, chat_id, message_id, variant_id, tool_name, arguments, result, is_error, extra_message_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), new_chat_id, new_msg_id, new_variant_id, tc["tool_name"],
                     tc["arguments"], tc["result"], tc["is_error"], tc.get("extra_message_json"), tc["created_at"]),
                )

    return new_chat_id


async def create_attachment(
    db: aiosqlite.Connection,
    chat_id: str,
    filename: str,
    file_data: bytes,
    mime_type: str | None = None,
) -> dict:
    attachment_id = str(uuid.uuid4())
    suffix = Path(filename).suffix.lower() or ".bin"
    mime = mime_type or "application/octet-stream"
    file_path = str(ATTACHMENTS_DIR / f"{attachment_id}{suffix}")
    Path(file_path).write_bytes(file_data)
    await db.execute(
        "INSERT INTO message_attachments (id, chat_id, message_id, variant_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (attachment_id, chat_id, None, None, file_path, mime, now_iso()),
    )
    return {"id": attachment_id, "file_path": file_path, "mime_type": mime, "filename": filename}


async def delete_attachment(db: aiosqlite.Connection, chat_id: str, attachment_id: str) -> None:
    async with db.execute(
        "SELECT file_path FROM message_attachments WHERE id = ? AND chat_id = ?",
        (attachment_id, chat_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "Attachment not found")
    file_path = row["file_path"]
    await db.execute("DELETE FROM message_attachments WHERE id = ?", (attachment_id,))
    async with db.execute("SELECT COUNT(*) FROM message_attachments WHERE file_path = ?", (file_path,)) as cur:
        count = (await cur.fetchone())[0]
    if count == 0:
        Path(file_path).unlink(missing_ok=True)


async def bind_attachments_to_message(
    db: aiosqlite.Connection,
    chat_id: str,
    message_id: str,
    variant_id: str,
    attachment_ids: list[str],
) -> None:
    if not attachment_ids:
        return
    placeholders = ",".join("?" * len(attachment_ids))
    await db.execute(
        f"UPDATE message_attachments SET message_id = ?, variant_id = ? WHERE id IN ({placeholders})",
        [message_id, variant_id] + attachment_ids,
    )


async def upsert_variant(
    chat_id: str,
    asst_msg_id: str,
    variant_index: int,
    content: str,
    regenerate: bool,
    model_name: str = "",
    variant_id: str | None = None,
    reasoning: str | None = None,
    segments_json: str | None = None,
    db: aiosqlite.Connection | None = None,
) -> str:
    save_now = now_iso()
    async with _db_conn(db) as conn:
        cur = await conn.execute(
            "SELECT id FROM message_variants WHERE message_id = ? AND variant_index = ?",
            (asst_msg_id, variant_index),
        )
        existing = await cur.fetchone()

        if existing:
            vid = existing[0]
            await conn.execute(
                "UPDATE message_variants SET content = ?, model_name = ?, created_at = ?, reasoning = ?, segments_json = ? WHERE id = ?",
                (content, model_name or None, save_now, reasoning, segments_json, vid),
            )
        else:
            vid = variant_id or str(uuid.uuid4())
            await conn.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at, model_name, reasoning, segments_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (vid, asst_msg_id, variant_index, content, save_now, model_name or None, reasoning, segments_json),
            )
            if regenerate and variant_index > 0:
                async with conn.execute("SELECT active_index FROM messages WHERE id = ?", (asst_msg_id,)) as act:
                    row = await act.fetchone()
                if row:
                    async with conn.execute(
                        "SELECT * FROM message_attachments WHERE variant_id = (SELECT id FROM message_variants WHERE message_id = ? AND variant_index = ?) ORDER BY created_at",
                        (asst_msg_id, row[0]),
                    ) as att_cur:
                        old_attachments = [dict(r) for r in await att_cur.fetchall()]
                    for att in old_attachments:
                        await conn.execute(
                            "INSERT INTO message_attachments (id, chat_id, message_id, variant_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), chat_id, asst_msg_id, vid, att["file_path"], att["mime_type"], save_now),
                        )

        if content or reasoning:
            await conn.execute(
                "UPDATE messages SET active_index = ? WHERE id = ?",
                (variant_index, asst_msg_id),
            )
        await conn.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (save_now, chat_id))
        await conn.commit()
    return vid


async def rollback_assistant(
    asst_msg_id: str | None,
    db: aiosqlite.Connection | None = None,
) -> None:
    if not asst_msg_id:
        return
    async with _db_conn(db) as conn:
        await conn.execute("DELETE FROM messages WHERE id = ?", (asst_msg_id,))
        await conn.commit()


async def save_usage(
    chat_id: str,
    message_id: str,
    variant_id: str,
    provider_id: str | None,
    provider_type: str | None,
    model_name: str | None,
    usage: dict,
    tool_iteration: int = 0,
    db: aiosqlite.Connection | None = None,
) -> None:
    import logging
    import sqlite3
    logger = logging.getLogger("focus.db.chats")

    row_id = str(uuid.uuid4())
    now = now_iso()
    cost = usage.get("cost")
    cost_details_raw = usage.get("cost_details")
    cost_details_str = json.dumps(cost_details_raw) if cost_details_raw is not None else None
    prompt = usage.get("prompt_tokens", 0)
    completion = usage.get("completion_tokens", 0)
    total = usage.get("total_tokens", 0)
    cached = usage.get("cached_tokens", 0)

    cache_pct = f"{cached / prompt * 100:.0f}%" if prompt > 0 else "-"
    tag = f"{provider_type or '?'}/{model_name or '?'}"
    cost_str = f" | cost=${cost:.5f}" if cost is not None else ""
    iter_str = f" (iter={tool_iteration})" if tool_iteration else ""
    logger.info(
        "USAGE %s | p=%s + c=%s = t=%s | cache=%s (%s)%s%s",
        tag, prompt, completion, total, cached, cache_pct, cost_str, iter_str,
    )

    try:
        async with _db_conn(db) as conn:
            params = (
                row_id, chat_id, message_id, variant_id,
                provider_id, provider_type, model_name,
                prompt, completion, total,
                cached, usage.get("reasoning_tokens", 0),
                cost, cost_details_str, tool_iteration, now,
            )
            sql = """INSERT INTO generation_usage
                   (id, chat_id, message_id, variant_id, provider_id, provider_type,
                    model_name, prompt_tokens, completion_tokens, total_tokens,
                    cached_tokens, reasoning_tokens, cost, cost_details,
                    tool_iteration, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            try:
                await conn.execute(sql, params)
            except sqlite3.IntegrityError:
                await conn.execute(sql, (params[0], params[1], params[2], None) + params[4:])
            await conn.commit()
    except Exception:
        logger.exception("Failed to persist generation_usage for message_id=%s", message_id)


async def persist_tool_calls(
    chat_id: str,
    asst_msg_id: str,
    variant_id: str | None,
    tool_calls_list: list,
    results: list,
    db: aiosqlite.Connection | None = None,
) -> None:
    save_now = now_iso()
    async with _db_conn(db) as conn:
        for call, result in zip(tool_calls_list, results):
            extra_msg = json.dumps(result.extra_message) if result.extra_message else None
            await conn.execute(
                """INSERT INTO tool_calls
                   (id, chat_id, message_id, variant_id, tool_name, arguments, result, is_error, extra_message_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), chat_id, asst_msg_id, variant_id, call.name,
                 json.dumps(call.arguments), result.content, int(result.is_error), extra_msg, save_now),
            )
        await conn.commit()
