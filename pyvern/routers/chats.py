import json
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from pyvern.database import get_db
from pyvern.models import ChatCreate, MessageEdit, SwipeRequest
from pyvern.card_parser import normalise_card

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Chats ─────────────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
async def create_chat(body: ChatCreate, db: aiosqlite.Connection = Depends(get_db)):
    chat_id = str(uuid.uuid4())
    now = _now()
    await db.execute(
        "INSERT INTO chats (id, title, character_id, persona_id, preset_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (chat_id, body.title or "New Chat", body.character_id, body.persona_id, body.preset_id, now, now),
    )

    # Seed greeting variants from first_mes + alternate_greetings
    if body.character_id:
        async with db.execute(
            "SELECT card_json FROM characters WHERE id = ?", (body.character_id,)
        ) as cur:
            row = await cur.fetchone()
        if row:
            card = normalise_card(json.loads(row["card_json"]))
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
    async with db.execute(
        "SELECT id, title, character_id, preset_id, created_at, updated_at FROM chats ORDER BY updated_at DESC"
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


@router.get("/{chat_id}")
async def get_chat(chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)) as cur:
        chat = await cur.fetchone()
    if not chat:
        raise HTTPException(404, "Chat not found")

    async with db.execute(
        """SELECT m.id, m.role, m.position, m.active_index, m.created_at,
                  mv.content,
                  (SELECT COUNT(*) FROM message_variants WHERE message_id = m.id) AS variant_count
           FROM messages m
           JOIN message_variants mv
             ON mv.message_id = m.id AND mv.variant_index = m.active_index
           WHERE m.chat_id = ?
           ORDER BY m.position""",
        (chat_id,),
    ) as cur:
        messages = [dict(r) for r in await cur.fetchall()]

    result = dict(chat)
    result["messages"] = messages
    return result


@router.patch("/{chat_id}")
async def update_chat(chat_id: str, body: dict, db: aiosqlite.Connection = Depends(get_db)):
    allowed = {"title", "preset_id", "character_id", "persona_id"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if updates:
        cols = ", ".join(f"{k} = ?" for k in updates)
        vals = list(updates.values()) + [_now(), chat_id]
        await db.execute(f"UPDATE chats SET {cols}, updated_at = ? WHERE id = ?", vals)
        await db.commit()
    return {"ok": True}


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    await db.execute("DELETE FROM chats WHERE id = ?", (chat_id,))
    await db.commit()


# ── Messages ──────────────────────────────────────────────────────────────────

@router.delete("/{chat_id}/messages/{message_id}", status_code=204)
async def delete_message(
    chat_id: str,
    message_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    """Delete a message and all messages after it (for retry/truncation)."""
    async with db.execute(
        "SELECT position FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Message not found")

    await db.execute(
        "DELETE FROM messages WHERE chat_id = ? AND position >= ?", (chat_id, row["position"])
    )
    await db.commit()


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
        "SELECT MAX(variant_index) FROM message_variants WHERE message_id = ?", (message_id,)
    ) as cur:
        max_row = await cur.fetchone()

    new_index = (max_row[0] or 0) + 1
    now = _now()

    await db.execute(
        "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), message_id, new_index, body.content, now),
    )
    await db.execute(
        "UPDATE messages SET active_index = ? WHERE id = ?", (new_index, message_id)
    )
    await db.execute(
        "UPDATE chats SET updated_at = ? WHERE id = ?", (now, chat_id)
    )
    await db.commit()
    return {"ok": True, "variant_index": new_index}


@router.post("/{chat_id}/messages/{message_id}/swipe")
async def swipe_message(
    chat_id: str,
    message_id: str,
    body: SwipeRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    """
    Navigate between existing variants.
    Returns needs_generation=True when swiping past the last variant,
    so the client knows to fire a /stream request.
    """
    async with db.execute(
        "SELECT active_index, position FROM messages WHERE id = ? AND chat_id = ?", (message_id, chat_id)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Message not found")

    current = row["active_index"]
    is_greeting = row["position"] == 0

    async with db.execute(
        "SELECT MAX(variant_index) FROM message_variants WHERE message_id = ?", (message_id,)
    ) as cur:
        max_row = await cur.fetchone()
    max_index = max_row[0] or 0

    if body.direction == "prev":
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
