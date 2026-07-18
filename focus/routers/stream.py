import json
import logging
import uuid

import aiosqlite
import tiktoken
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from focus.core.database import DB_PATH, get_db
from focus.core.logger import get_logger
from focus.core.models import ItemizerRequest, StreamRequest
from focus.core.utils import (
    AUDIO_TOKEN_ESTIMATE,
    _image_dims_from_data_url,
    estimate_image_tokens,
    now_iso,
    resolve_secret_key,
)
from focus.providers import create_provider
from focus.routers.stream_utils import (
    apply_claude_caching,
    filter_unsupported_modalities,
    get_prompt_context,
)

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

    # ── User-controlled multimodal disable ──────────────────────────────────────
    s = dict(body.samplers) if body.samplers else {}
    if s.pop("disable_multimodal", False):
        messages = filter_unsupported_modalities(messages, ["text"])

    # ── OpenRouter modality filter ─────────────────────────────────────────────
    if prov_dict.get("type") == "openrouter":
        from focus.routers.providers import get_openrouter_model_modalities

        modalities = await get_openrouter_model_modalities(prov_dict.get("model", ""))
        if modalities:
            messages = filter_unsupported_modalities(messages, modalities)

        # Claude prompt caching
        s = dict(body.samplers) if body.samplers else {}
        if s.pop("cache_enabled", False) and prov_dict.get("model", "").startswith("anthropic/claude"):
            messages = apply_claude_caching(
                messages,
                True,
                s.pop("cache_ttl", "ephemeral"),
                s.pop("cache_depth", 5),
            )

    # Strip internal metadata tags — set by get_prompt_context / assemble_prompt
    for msg in messages:
        msg.pop("_greeting", None)
    # Strip provider-internal keys (used only by google provider, leak to others)
    if prov_dict.get("type") != "google":
        for msg in messages:
            msg.pop("thought_signature", None)
            msg.pop("reasoning", None)

    # ── Gen params ────────────────────────────────────────────────────────────
    gen_kwargs: dict = {}
    use_stream = True
    if body.samplers:
        s = dict(body.samplers)
        use_stream = s.pop("stream_enabled", True)
        s.pop("disable_multimodal", None)
        s.pop("cache_enabled", None)
        s.pop("cache_ttl", None)
        s.pop("cache_depth", None)
        gen_kwargs.update(s)

    # OpenRouter sticky routing: pin requests to the same endpoint for cache warmth
    if prov_dict.get("type") == "openrouter":
        gen_kwargs["session_id"] = body.chat_id

    # ── Non-streaming path ─────────────────────────────────────────────────────
    if not use_stream:
        collected: list[str] = []
        final_asst_msg_id = asst_msg_id

        try:
            logger.debug(f"Starting non-stream completion for chat_id={body.chat_id} provider={prov_dict['name']}")
            async for token in provider.stream_complete(messages, **gen_kwargs):
                collected.append(token)
        except Exception as e:
            logger.exception("Non-stream completion failed for chat_id=%s", body.chat_id)
            if not body.regenerate:
                await _rollback_assistant(final_asst_msg_id)
            raise HTTPException(500, str(e) or repr(e))

        full = "".join(collected)

        try:
            await _save_assistant_variant(
                body.chat_id,
                final_asst_msg_id,
                next_variant_index,
                full,
                body.regenerate,
                prov_dict.get("model", ""),
            )
        except Exception as e:
            logger.exception("Failed to save non-stream result for chat_id=%s", body.chat_id)
            if not body.regenerate:
                await _rollback_assistant(final_asst_msg_id)
            raise HTTPException(500, f"Generation succeeded but save failed: {str(e) or repr(e)}")

        return JSONResponse(
            {
                "done": True,
                "message_id": final_asst_msg_id,
                "variant_index": next_variant_index,
                "user_message_id": user_msg_id if not body.regenerate else None,
                "full_text": full,
            }
        )

    # ── Streaming path ──────────────────────────────────────────────────────────

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
        logger.debug("Provider: %s (%s)", prov_dict.get("name"), prov_dict.get("model"))
        logger.debug("Samplers:\n%s", json.dumps(gen_kwargs, indent=2))
        logger.debug("Messages:\n%s", json.dumps(_truncate_b64(messages), indent=2, ensure_ascii=False))
        logger.debug("==========================================")

    async def generate():
        yield f"data: {json.dumps({'type': 'start', 'message_id': final_asst_msg_id, 'user_message_id': user_msg_id if not body.regenerate else None})}\n\n"
        _completed = False
        _handled = False
        try:
            try:
                logger.debug(f"Starting generation stream for chat_id={body.chat_id} provider={prov_dict['name']}")
                async for token in provider.stream_complete(messages, **gen_kwargs):
                    collected.append(token)
                    yield f"data: {json.dumps({'token': token})}\n\n"
            except Exception as e:
                _handled = True
                logger.exception("Stream exception for chat_id=%s", body.chat_id)
                if not body.regenerate:
                    await _rollback_assistant(final_asst_msg_id)
                err_msg = str(e)
                if not err_msg or err_msg == "()":
                    err_msg = repr(e)
                yield f"data: {json.dumps({'error': err_msg})}\n\n"
                return

            full = "".join(collected)

            try:
                await _save_assistant_variant(
                    body.chat_id,
                    final_asst_msg_id,
                    next_variant_index,
                    full,
                    body.regenerate,
                    prov_dict.get("model", ""),
                )
            except Exception as e:
                _handled = True
                logger.exception("Failed to save stream result for chat_id=%s", body.chat_id)
                if not body.regenerate:
                    await _rollback_assistant(final_asst_msg_id)
                err_msg = str(e) or repr(e)
                yield f"data: {json.dumps({'error': f'Generation succeeded but save failed: {err_msg}'})}\n\n"
                return

            yield f"data: {json.dumps({'done': True, 'message_id': final_asst_msg_id, 'variant_index': next_variant_index})}\n\n"
            _completed = True
        finally:
            if not _completed and not _handled:
                logger.info("Client disconnected, stream terminated for chat_id=%s", body.chat_id)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _save_assistant_variant(
    chat_id: str,
    asst_msg_id: str,
    variant_index: int,
    content: str,
    regenerate: bool,
    model_name: str = "",
) -> str:
    new_variant_id = str(uuid.uuid4())
    save_now = now_iso()

    async with aiosqlite.connect(DB_PATH) as save_db:
        await save_db.execute("PRAGMA foreign_keys=ON")
        await save_db.execute(
            "INSERT INTO message_variants (id, message_id, variant_index, content, created_at, model_name) VALUES (?, ?, ?, ?, ?, ?)",
            (new_variant_id, asst_msg_id, variant_index, content, save_now, model_name or None),
        )

        if regenerate and variant_index > 0:
            async with save_db.execute("SELECT active_index FROM messages WHERE id = ?", (asst_msg_id,)) as cur:
                row = await cur.fetchone()
            if row:
                async with save_db.execute(
                    "SELECT * FROM message_attachments WHERE variant_id = (SELECT id FROM message_variants WHERE message_id = ? AND variant_index = ?) ORDER BY created_at",
                    (asst_msg_id, row[0]),
                ) as att_cur:
                    old_attachments = [dict(r) for r in await att_cur.fetchall()]

                for att in old_attachments:
                    await save_db.execute(
                        "INSERT INTO message_attachments (id, chat_id, message_id, variant_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(uuid.uuid4()),
                            chat_id,
                            asst_msg_id,
                            new_variant_id,
                            att["file_path"],
                            att["mime_type"],
                            save_now,
                        ),
                    )

        await save_db.execute(
            "UPDATE messages SET active_index = ? WHERE id = ?",
            (variant_index, asst_msg_id),
        )
        await save_db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (save_now, chat_id))
        await save_db.commit()

    return new_variant_id


async def _rollback_assistant(asst_msg_id: str | None):
    """Delete the empty assistant row that get_prompt_context eagerly inserts
    before the provider is called. Called from the stream's exception paths so
    a failed request leaves the DB in pre-send state (user message is kept)."""
    if not asst_msg_id:
        return
    async with aiosqlite.connect(DB_PATH) as rollback_db:
        await rollback_db.execute("PRAGMA foreign_keys=ON")
        await rollback_db.execute("DELETE FROM messages WHERE id = ?", (asst_msg_id,))
        await rollback_db.commit()


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
                    dims = _image_dims_from_data_url(part["image_url"]["url"])
                    img_tokens = estimate_image_tokens(*dims) if dims else 258
                    tokens += img_tokens
                    clean_parts.append({"type": "image", "text": "[IMAGE ATTACHMENT]", "tokens": img_tokens})
                elif part["type"] == "input_audio":
                    tokens += AUDIO_TOKEN_ESTIMATE
                    clean_parts.append(
                        {
                            "type": "audio",
                            "text": "[AUDIO ATTACHMENT]",
                            "tokens": AUDIO_TOKEN_ESTIMATE,
                        }
                    )

        total_tokens += tokens
        clean_messages.append({"role": role, "parts": clean_parts, "tokens": tokens})

    return JSONResponse({"total_tokens": total_tokens, "messages": clean_messages})
