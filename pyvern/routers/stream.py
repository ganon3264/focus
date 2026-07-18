import json
import logging
import uuid

import aiosqlite
import tiktoken
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from pyvern.database import get_db, DB_PATH
from pyvern.models import StreamRequest, ItemizerRequest
from pyvern.providers import create_provider
from pyvern.logger import get_logger
from pyvern.utils import now_iso, resolve_secret_key, IMAGE_TOKEN_ESTIMATE, AUDIO_TOKEN_ESTIMATE
from pyvern.routers.stream_utils import get_prompt_context

router = APIRouter()
logger = get_logger("routers.stream")


@router.post("/stream")
async def stream(body: StreamRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Generate a streaming completion from the selected provider.

    Loads the provider config, resolves secrets, builds the prompt context,
    streams tokens via SSE, and persists the result as a message variant.
    """
    # ── Provider ─────────────────────────────────────────────────────────────
    async with db.execute("SELECT * FROM providers WHERE id = ?", (body.provider_id,)) as cur:
        prov_row = await cur.fetchone()
    if not prov_row:
        raise HTTPException(404, "Provider not found")

    prov_dict = dict(prov_row)
    prov_dict["api_key"] = await resolve_secret_key(db, prov_dict.get("api_key") or "")

    provider = create_provider(prov_dict)

    # ── Build prompt context (includes user message persistence) ─────────────
    ctx = await get_prompt_context(
        db, body.chat_id, body.regenerate, body.user_message, body.attachment_ids, persist=True
    )
    messages = ctx["messages"]
    asst_msg_id = ctx["asst_msg_id"]
    next_variant_index = ctx["next_variant_index"]
    user_msg_id = ctx["user_msg_id"]

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
        save_now = now_iso()
        new_variant_id = str(uuid.uuid4())

        try:
            async with aiosqlite.connect(DB_PATH) as save_db:
                await save_db.execute("PRAGMA foreign_keys=ON")
                await save_db.execute(
                    "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                    (new_variant_id, final_asst_msg_id, next_variant_index, full, save_now),
                )

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
        except Exception as e:
            logger.exception(f"Failed to save stream result for chat_id={body.chat_id}")
            err_msg = str(e) or repr(e)
            yield f"data: {json.dumps({'error': f'Generation succeeded but save failed: {err_msg}'})}\n\n"
            return

        yield f"data: {json.dumps({'done': True, 'message_id': final_asst_msg_id, 'variant_index': next_variant_index})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/itemize")
async def itemize_prompt(body: ItemizerRequest, db: aiosqlite.Connection = Depends(get_db)):
    ctx = await get_prompt_context(
        db, body.chat_id, body.regenerate, body.user_message, body.attachment_ids, persist=False
    )
    messages = ctx["messages"]

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
                    tokens += IMAGE_TOKEN_ESTIMATE
                    clean_parts.append({"type": "image", "text": "[IMAGE ATTACHMENT]", "tokens": IMAGE_TOKEN_ESTIMATE})
                elif part["type"] == "input_audio":
                    tokens += AUDIO_TOKEN_ESTIMATE
                    clean_parts.append({"type": "audio", "text": "[AUDIO ATTACHMENT]", "tokens": AUDIO_TOKEN_ESTIMATE})

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
