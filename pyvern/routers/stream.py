import json
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from pyvern.database import get_db, DB_PATH
from pyvern.models import StreamRequest
from pyvern.providers import create_provider
from pyvern.prompt_chain import assemble_prompt
from pyvern.card_parser import normalise_card

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_macros(card: dict, user_name: str = "User") -> dict:
    return {
        "char":        card.get("name", "Assistant"),
        "user":        user_name,
        "description": card.get("description", ""),
        "personality": card.get("personality", ""),
        "persona":     card.get("personality", ""),
        "scenario":    card.get("scenario", ""),
        "mes_example": card.get("mes_example", ""),
    }


@router.post("/stream")
async def stream(body: StreamRequest, db: aiosqlite.Connection = Depends(get_db)):
    # ── Validate chat ────────────────────────────────────────────────────────
    async with db.execute("SELECT * FROM chats WHERE id = ?", (body.chat_id,)) as cur:
        chat = await cur.fetchone()
    if not chat:
        raise HTTPException(404, "Chat not found")
    chat = dict(chat)

    # ── Provider ─────────────────────────────────────────────────────────────
    async with db.execute("SELECT * FROM providers WHERE id = ?", (body.provider_id,)) as cur:
        prov_row = await cur.fetchone()
    if not prov_row:
        raise HTTPException(404, "Provider not found")
    provider = create_provider(dict(prov_row))

    # ── Macros ────────────────────────────────────────────────────────────────
    macros: dict = {"char": "Assistant", "user": "User", "description": "",
                    "personality": "", "persona": "", "scenario": "", "mes_example": ""}
    if chat["character_id"]:
        async with db.execute(
            "SELECT card_json FROM characters WHERE id = ?", (chat["character_id"],)
        ) as cur:
            char_row = await cur.fetchone()
        if char_row:
            card = normalise_card(json.loads(char_row["card_json"]))
            macros = _build_macros(card)

    # ── Preset blocks ─────────────────────────────────────────────────────────
    preset_blocks: list[dict] = []
    if chat["preset_id"]:
        async with db.execute(
            "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position",
            (chat["preset_id"],),
        ) as cur:
            preset_blocks = [dict(r) for r in await cur.fetchall()]

    # ── Existing history ──────────────────────────────────────────────────────
    if body.regenerate:
        # Drop the last assistant message from history — we'll create a new variant
        async with db.execute(
            """SELECT m.id, m.role, m.position, mv.content
               FROM messages m
               JOIN message_variants mv
                 ON mv.message_id = m.id AND mv.variant_index = m.active_index
               WHERE m.chat_id = ?
               ORDER BY m.position""",
            (body.chat_id,),
        ) as cur:
            all_rows = await cur.fetchall()

        # Find last assistant message
        last_asst_id = None
        last_asst_variant_count = 0
        for r in reversed(all_rows):
            if r["role"] == "assistant":
                last_asst_id = r["id"]
                async with db.execute(
                    "SELECT COUNT(*) FROM message_variants WHERE message_id = ?", (r["id"],)
                ) as cnt_cur:
                    cnt_row = await cnt_cur.fetchone()
                last_asst_variant_count = cnt_row[0]
                break

        history = [
            {"role": r["role"], "content": r["content"]}
            for r in all_rows
            if r["id"] != last_asst_id
        ]
        asst_msg_id = last_asst_id  # add new variant to existing slot
        next_variant_index = last_asst_variant_count  # 0-indexed next slot
    else:
        async with db.execute(
            """SELECT m.id, m.role, mv.content
               FROM messages m
               JOIN message_variants mv
                 ON mv.message_id = m.id AND mv.variant_index = m.active_index
               WHERE m.chat_id = ?
               ORDER BY m.position""",
            (body.chat_id,),
        ) as cur:
            history_rows = await cur.fetchall()
        history = [{"role": r["role"], "content": r["content"]} for r in history_rows]
        asst_msg_id = None
        next_variant_index = 0

    # ── Save user message (not on regen) ──────────────────────────────────────
    now = _now()
    if not body.regenerate:
        async with db.execute(
            "SELECT MAX(position) FROM messages WHERE chat_id = ?", (body.chat_id,)
        ) as cur:
            pos_row = await cur.fetchone()
        next_pos = (pos_row[0] if pos_row[0] is not None else -1) + 1

        user_msg_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (user_msg_id, body.chat_id, "user", next_pos, 0, now),
        )
        await db.execute(
            "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), user_msg_id, 0, body.user_message, now),
        )

        # Create assistant message slot
        asst_msg_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (asst_msg_id, body.chat_id, "assistant", next_pos + 1, 0, now),
        )
        next_variant_index = 0

        history.append({"role": "user", "content": body.user_message})

    await db.commit()

    # ── Assemble final prompt ─────────────────────────────────────────────────
    messages = assemble_prompt(preset_blocks, history, macros)

    # ── Gen params ────────────────────────────────────────────────────────────
    gen_kwargs: dict = {}
    if body.max_tokens is not None:
        gen_kwargs["max_tokens"] = body.max_tokens
    if body.temperature is not None:
        gen_kwargs["temperature"] = body.temperature
    if body.top_p is not None:
        gen_kwargs["top_p"] = body.top_p

    # ── Stream ────────────────────────────────────────────────────────────────
    collected: list[str] = []
    final_asst_msg_id = asst_msg_id

    async def generate():
        try:
            async for token in provider.stream_complete(messages, **gen_kwargs):
                collected.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            return

        full = "".join(collected)
        save_now = _now()

        async with aiosqlite.connect(DB_PATH) as save_db:
            await save_db.execute("PRAGMA foreign_keys=ON")
            await save_db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), final_asst_msg_id, next_variant_index, full, save_now),
            )
            await save_db.execute(
                "UPDATE messages SET active_index = ? WHERE id = ?",
                (next_variant_index, final_asst_msg_id),
            )
            await save_db.execute(
                "UPDATE chats SET updated_at = ? WHERE id = ?", (save_now, body.chat_id)
            )
            await save_db.commit()

        yield f"data: {json.dumps({'done': True, 'message_id': final_asst_msg_id, 'variant_index': next_variant_index})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
