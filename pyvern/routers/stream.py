import json
import uuid
from datetime import datetime, timezone

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from pyvern.database import get_db, DB_PATH
from pyvern.models import StreamRequest
from pyvern.providers import create_provider
from pyvern.prompt_chain import assemble_prompt, _build_content
from pyvern.card_parser import normalise_card

router = APIRouter()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_macros(card: dict, persona: dict | None = None) -> dict:
    return {
        "char":        card.get("name", "Assistant"),
        "user":        persona["name"] if persona else "User",
        "persona":     persona["description"] if persona else "",
        "persona_id":  persona["id"] if persona else "",
        "description": card.get("description", ""),
        "personality": card.get("personality", ""),
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
    
    prov_dict = dict(prov_row)
    
    api_key = prov_dict.get("api_key") or ""
    if api_key.startswith("SECRET:"):
        secret_name = api_key[7:]
        async with db.execute("SELECT value FROM secrets WHERE name = ?", (secret_name,)) as cur:
            secret_row = await cur.fetchone()
            if secret_row:
                prov_dict["api_key"] = secret_row["value"]
            else:
                prov_dict["api_key"] = ""
                
    provider = create_provider(prov_dict)

    # ── Macros + char data ────────────────────────────────────────────────────
    char_data: dict = {"name": "Assistant", "description": "", "personality": "",
                       "scenario": "", "mes_example": "", "first_mes": ""}
    char_own_blocks: list[dict] = []

    if chat["character_id"]:
        char_data["id"] = chat["character_id"]
        async with db.execute(
            "SELECT card_json FROM characters WHERE id = ?", (chat["character_id"],)
        ) as cur:
            char_row = await cur.fetchone()
        if char_row:
            card_json = normalise_card(json.loads(char_row["card_json"]))
            char_data.update(card_json)

        async with db.execute(
            "SELECT * FROM char_blocks WHERE character_id = ? ORDER BY position, rowid",
            (chat["character_id"],),
        ) as cur:
            char_own_blocks = [dict(r) for r in await cur.fetchall()]

    macros = _build_macros(char_data)

    # ── Persona ───────────────────────────────────────────────────────────────
    persona: dict | None = None
    if chat["persona_id"]:
        async with db.execute(
            "SELECT * FROM personas WHERE id = ?", (chat["persona_id"],)
        ) as cur:
            row = await cur.fetchone()
            if row:
                persona = dict(row)
    if not persona:
        async with db.execute("SELECT * FROM personas ORDER BY created_at LIMIT 1") as cur:
            row = await cur.fetchone()
            if row:
                persona = dict(row)

    macros = _build_macros(char_data, persona)

    # ── Preset blocks ─────────────────────────────────────────────────────────
    preset_blocks: list[dict] = []
    if chat["preset_id"]:
        async with db.execute(
            "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid",
            (chat["preset_id"],),
        ) as cur:
            preset_blocks = [dict(r) for r in await cur.fetchall()]

    # ── Message Attachments ───────────────────────────────────────────────────
    msg_attachments: dict[str, list[dict]] = {}
    async with db.execute(
        "SELECT * FROM message_attachments WHERE chat_id = ? AND message_id IS NOT NULL ORDER BY created_at",
        (body.chat_id,),
    ) as cur:
        for r in await cur.fetchall():
            msg_attachments.setdefault(r["message_id"], []).append(dict(r))

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
            {"role": r["role"], "content": _build_content(r["content"], msg_attachments.get(r["id"], []))}
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
        history = [{"role": r["role"], "content": _build_content(r["content"], msg_attachments.get(r["id"], []))} for r in history_rows]
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

        # Only create a user message if there's actual text or attachments
        if body.user_message.strip() or body.attachment_ids:
            user_msg_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_msg_id, body.chat_id, "user", next_pos, 0, now),
            )
            await db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), user_msg_id, 0, body.user_message, now),
            )

            # Bind any attached files to the newly created user message
            if body.attachment_ids:
                placeholders = ",".join("?" * len(body.attachment_ids))
                await db.execute(
                    f"UPDATE message_attachments SET message_id = ? WHERE id IN ({placeholders})",
                    [user_msg_id] + body.attachment_ids
                )
                
                async with db.execute(
                    f"SELECT * FROM message_attachments WHERE id IN ({placeholders}) ORDER BY created_at",
                    body.attachment_ids
                ) as cur:
                    new_attachments = [dict(r) for r in await cur.fetchall()]
            else:
                new_attachments = []
                
            history.append({"role": "user", "content": _build_content(body.user_message, new_attachments)})
            next_pos += 1 # advance position for assistant message

        # Create assistant message slot
        asst_msg_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (asst_msg_id, body.chat_id, "assistant", next_pos, 0, now),
        )
        next_variant_index = 0

    await db.commit()

    # ── Block images ──────────────────────────────────────────────────────────
    all_block_ids = [b["id"] for b in preset_blocks] + [b["id"] for b in char_own_blocks]
    if chat["character_id"]:
        all_block_ids.append(chat["character_id"])
    if chat["persona_id"]:
        all_block_ids.append(chat["persona_id"])
        
    block_images: dict[str, list[dict]] = {}
    if all_block_ids:
        placeholders = ",".join("?" * len(all_block_ids))
        async with db.execute(
            f"SELECT * FROM block_images WHERE block_id IN ({placeholders}) ORDER BY position",
            all_block_ids,
        ) as cur:
            for row in await cur.fetchall():
                r = dict(row)
                block_images.setdefault(r["block_id"], []).append(r)

    # ── Assemble final prompt ─────────────────────────────────────────────────
    messages = assemble_prompt(preset_blocks, history, char_data, char_own_blocks, macros, block_images)

    # ── Gen params ────────────────────────────────────────────────────────────
    gen_kwargs: dict = {}
    if body.samplers:
        gen_kwargs.update(body.samplers)

    # ── Stream ────────────────────────────────────────────────────────────────
    collected: list[str] = []
    final_asst_msg_id = asst_msg_id

    async def generate():
        yield f"data: {json.dumps({'type': 'start', 'message_id': final_asst_msg_id})}\n\n"
        try:
            async for token in provider.stream_complete(messages, **gen_kwargs):
                collected.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:
            err_msg = str(e)
            if not err_msg or err_msg == "()":
                err_msg = repr(e)
            yield f"data: {json.dumps({'error': err_msg})}\n\n"
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
