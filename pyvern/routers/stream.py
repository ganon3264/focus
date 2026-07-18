import json
import logging
import uuid
from datetime import datetime, timezone

import aiosqlite
import tiktoken
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from pyvern.database import get_db, DB_PATH
from pyvern.models import StreamRequest, ItemizerRequest
from pyvern.providers import create_provider
from pyvern.prompt_chain import assemble_prompt, _build_content
from pyvern.card_parser import normalise_card
from pyvern.logger import get_logger

router = APIRouter()
logger = get_logger("routers.stream")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


from pyvern.macros import build_base_macros


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

    macros = build_base_macros(char_data)

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

    macros = build_base_macros(char_data, persona)

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
        "SELECT * FROM message_attachments WHERE chat_id = ? AND variant_id IS NOT NULL ORDER BY created_at",
        (body.chat_id,),
    ) as cur:
        for r in await cur.fetchall():
            msg_attachments.setdefault(r["variant_id"], []).append(dict(r))

    # ── Existing history ──────────────────────────────────────────────────────
    if body.regenerate:
        # Drop the last assistant message from history — we'll create a new variant
        async with db.execute(
            """SELECT m.id, m.role, m.position, mv.content, mv.id as variant_id
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
            {"role": r["role"], "content": _build_content(r["content"], msg_attachments.get(r["variant_id"], []))}
            for r in all_rows
            if r["id"] != last_asst_id
        ]
        asst_msg_id = last_asst_id  # add new variant to existing slot
        next_variant_index = last_asst_variant_count  # 0-indexed next slot
    else:
        async with db.execute(
            """SELECT m.id, m.role, mv.content, mv.id as variant_id
               FROM messages m
               JOIN message_variants mv
                 ON mv.message_id = m.id AND mv.variant_index = m.active_index
               WHERE m.chat_id = ?
               ORDER BY m.position""",
            (body.chat_id,),
        ) as cur:
            history_rows = await cur.fetchall()
        history = [{"role": r["role"], "content": _build_content(r["content"], msg_attachments.get(r["variant_id"], []))} for r in history_rows]
        asst_msg_id = None
        next_variant_index = 0

    # ── Save user message (not on regen) ──────────────────────────────────────
    now = _now()
    if not body.regenerate:
        user_msg_id = None
        async with db.execute(
            "SELECT MAX(position) FROM messages WHERE chat_id = ?", (body.chat_id,)
        ) as cur:
            pos_row = await cur.fetchone()
        next_pos = (pos_row[0] if pos_row[0] is not None else -1) + 1

        # Only create a user message if there's actual text or attachments
        if body.user_message.strip() or body.attachment_ids:
            user_msg_id = str(uuid.uuid4())
            user_variant_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_msg_id, body.chat_id, "user", next_pos, 0, now),
            )
            await db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_variant_id, user_msg_id, 0, body.user_message, now),
            )

            # Bind any attached files to the newly created user message
            if body.attachment_ids:
                placeholders = ",".join("?" * len(body.attachment_ids))
                await db.execute(
                    f"UPDATE message_attachments SET message_id = ?, variant_id = ? WHERE id IN ({placeholders})",
                    [user_msg_id, user_variant_id] + body.attachment_ids
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
    
    # ── Debug Payload Dumper ──────────────────────────────────────────────────
    if logger.isEnabledFor(logging.DEBUG):
        import copy
        
        def _truncate_b64(msgs):
            dump_msgs = copy.deepcopy(msgs)
            for m in dump_msgs:
                content = m.get("content")
                if isinstance(content, list):
                    for part in content:
                        if part.get("type") == "image_url":
                            url = part["image_url"].get("url", "")
                            if url.startswith("data:") and ";base64," in url:
                                mime, _ = url.split(";base64,", 1)
                                part["image_url"]["url"] = f"{mime};base64,<data truncated>"
                        elif part.get("type") == "input_audio":
                            part["input_audio"]["data"] = "<data truncated>"
            return dump_msgs

        logger.debug("OUTBOUND PAYLOAD =========================")
        logger.debug(f"Provider: {prov_dict.get('name')} ({prov_dict.get('model')})")
        logger.debug(f"Samplers:\n{json.dumps(gen_kwargs, indent=2)}")
        logger.debug(f"Messages:\n{json.dumps(_truncate_b64(messages), indent=2, ensure_ascii=False)}")
        logger.debug("==========================================")

    async def generate():
        yield f"data: {json.dumps({'type': 'start', 'message_id': final_asst_msg_id, 'user_message_id': user_msg_id if not body.regenerate else None})}\n\n"
        try:
            logger.debug(f"Starting generation stream for chat_id={body.chat_id} provider={prov_dict['name']}")
            async for token in provider.stream_complete(messages, **gen_kwargs):
                collected.append(token)
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:
            logger.exception(f"Stream exception for chat_id={body.chat_id}")
            err_msg = str(e)
            if not err_msg or err_msg == "()":
                err_msg = repr(e)
            yield f"data: {json.dumps({'error': err_msg})}\n\n"
            return

        full = "".join(collected)
        save_now = _now()
        new_variant_id = str(uuid.uuid4())

        async with aiosqlite.connect(DB_PATH) as save_db:
            await save_db.execute("PRAGMA foreign_keys=ON")
            await save_db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (new_variant_id, final_asst_msg_id, next_variant_index, full, save_now),
            )
            
            # If this is a regeneration, duplicate the attachments from the previous active variant
            if body.regenerate and next_variant_index > 0:
                async with save_db.execute(
                    "SELECT active_index FROM messages WHERE id = ?", (final_asst_msg_id,)
                ) as cur:
                    row = await cur.fetchone()
                    if row:
                        async with save_db.execute(
                            "SELECT * FROM message_attachments WHERE variant_id = (SELECT id FROM message_variants WHERE message_id = ? AND variant_index = ?) ORDER BY created_at",
                            (final_asst_msg_id, row[0])
                        ) as att_cur:
                            old_attachments = [dict(r) for r in await att_cur.fetchall()]
                            
                        for att in old_attachments:
                            await save_db.execute(
                                "INSERT INTO message_attachments (id, chat_id, message_id, variant_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                                (str(uuid.uuid4()), body.chat_id, final_asst_msg_id, new_variant_id, att["file_path"], att["mime_type"], save_now),
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

@router.post("/itemize")
async def itemize_prompt(body: ItemizerRequest, db: aiosqlite.Connection = Depends(get_db)):
    from pyvern.routers.stream_utils import get_prompt_context
    messages = await get_prompt_context(db, body.chat_id, body.regenerate, body.user_message, body.attachment_ids)
    
    # Strip base64 and estimate tokens
    enc = tiktoken.get_encoding("cl100k_base")
    total_tokens = 0
    clean_messages = []
    
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        tokens = 0
        clean_parts = []
        
        if isinstance(content, str):
            tokens = len(enc.encode(content))
            clean_parts.append({"type": "text", "text": content})
        else:
            for part in content:
                if part["type"] == "text":
                    t_count = len(enc.encode(part["text"]))
                    tokens += t_count
                    clean_parts.append({"type": "text", "text": part["text"], "tokens": t_count})
                elif part["type"] == "image_url":
                    # Rough heuristic for image
                    tokens += 85
                    clean_parts.append({"type": "image", "text": "[IMAGE ATTACHMENT]", "tokens": 85})
                elif part["type"] == "input_audio":
                    tokens += 100
                    clean_parts.append({"type": "audio", "text": "[AUDIO ATTACHMENT]", "tokens": 100})
                    
        total_tokens += tokens
        clean_messages.append({
            "role": role,
            "parts": clean_parts,
            "tokens": tokens
        })
        
    return JSONResponse({
        "total_tokens": total_tokens,
        "messages": clean_messages
    })
