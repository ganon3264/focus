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
from focus.core.message_render import strip_think_blocks
from focus.routers.providers import get_openrouter_model_modalities
from focus.routers.stream_utils import (
    apply_claude_caching,
    filter_unsupported_modalities,
    get_prompt_context,
)
from focus.tools import (
    MAX_TOOL_ITERATIONS,
    ToolResult,
    active_tools,
    build_tool_result,
)
from focus.tools.builtin import ALL_TOOLS
from focus.tools.provider_adapter import (
    to_provider_tools,
    to_provider_tool_results,
)

router = APIRouter()
logger = get_logger("routers.stream")


@router.post("/stream")
async def stream(body: StreamRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Generate a streaming completion from the selected provider.

    Loads the provider config, resolves secrets, builds the prompt context,
    streams tokens via SSE, and persists the result as a message variant.
    Supports an iterative tool-calling loop when tools_enabled=True.
    """
    # ── Provider ─────────────────────────────────────────────────────────────
    async with db.execute("SELECT * FROM providers WHERE id = ?", (body.provider_id,)) as cur:
        prov_row = await cur.fetchone()
    if not prov_row:
        raise HTTPException(404, "Provider not found")

    prov_dict = dict(prov_row)
    prov_dict["api_key"] = await resolve_secret_key(db, prov_dict.get("api_key") or "")

    provider = create_provider(prov_dict)

    logger.debug(
        "stream: chat_id=%s provider=%s model=%s regenerate=%s user_message=%r attachment_ids=%s",
        body.chat_id, prov_dict["name"], prov_dict.get("model", "?"),
        body.regenerate, body.user_message, body.attachment_ids,
    )

    ctx = await get_prompt_context(
        db, body.chat_id, body.regenerate, body.user_message, body.attachment_ids, persist=True
    )
    messages = ctx["messages"]
    asst_msg_id = ctx["asst_msg_id"]
    next_variant_index = ctx["next_variant_index"]
    user_msg_id = ctx["user_msg_id"]

    logger.debug(
        "stream: ctx returned asst_msg_id=%s user_msg_id=%s next_variant_index=%d messages=%d",
        asst_msg_id, user_msg_id, next_variant_index, len(messages),
    )

    # Continue: update the current variant in-place instead of creating a new swipe
    if body.continue_text and body.regenerate and asst_msg_id:
        async with db.execute("SELECT active_index FROM messages WHERE id = ?", (asst_msg_id,)) as cur:
            row = await cur.fetchone()
        if row is not None:
            next_variant_index = row[0]

    s = dict(body.samplers) if body.samplers else {}
    if s.pop("disable_multimodal", False):
        messages = filter_unsupported_modalities(messages, ["text"])

    if prov_dict.get("type") == "openrouter":
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

    for msg in messages:
        msg.pop("_greeting", None)
    if prov_dict.get("type", "") not in ("google_aistudio", "google_vertex"):
        for msg in messages:
            msg.pop("thought_signature", None)
            msg.pop("reasoning", None)

    if body.continue_text and body.regenerate and provider.supports_prefill:
        messages.append({"role": "assistant", "content": body.continue_text})

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

    # ── Tool calling setup ─────────────────────────────────────────────────
    tools_enabled = body.tools_enabled
    tool_read_only = body.tool_read_only

    # Disable tools for providers that don't support them
    if tools_enabled and not provider.supports_tools:
        tools_enabled = False
        logger.debug("Tools disabled: provider %s does not support tool calling", prov_dict.get("type"))

    if tools_enabled:
        cur_tools = active_tools(ALL_TOOLS, tool_read_only)
        tools_payload = to_provider_tools(cur_tools)
        tools_by_name = {t.name: t for t in cur_tools}
        if tools_payload:
            gen_kwargs["tools"] = tools_payload
            gen_kwargs["tool_choice"] = "auto"
    else:
        cur_tools = []
        tools_payload = []
        tools_by_name = {}

    if not use_stream:
        collected: list[str] = []
        final_asst_msg_id = asst_msg_id
        loop_messages = list(messages)
        variant_id = str(uuid.uuid4())

        for _iteration in range(MAX_TOOL_ITERATIONS if tools_enabled else 1):
            iter_collected: list[str] = []
            tool_calls_list: list | None = None

            try:
                logger.debug(
                    "Non-stream iteration for chat_id=%s provider=%s",
                    body.chat_id, prov_dict["name"],
                )
                async for event in provider.stream_complete(loop_messages, **gen_kwargs):
                    if event["type"] == "token":
                        iter_collected.append(event["text"])
                    elif event["type"] == "tool_calls":
                        tool_calls_list = event["calls"]
                        break
                    elif event["type"] == "done":
                        tool_calls_list = None
                        break
            except Exception as e:
                logger.exception("Non-stream completion failed for chat_id=%s", body.chat_id)
                if not body.regenerate:
                    await _rollback_assistant(final_asst_msg_id)
                raise HTTPException(500, str(e) or repr(e))

            if not tool_calls_list:
                collected.extend(iter_collected)
                break

            collected.extend(iter_collected)
            collected.append("%%%TOOL_BOUNDARY%%%")
            tool_calls_list = list(tool_calls_list)
            logger.debug(
                "Tool round (%d calls) for chat_id=%s",
                len(tool_calls_list), body.chat_id,
            )

            await _apply_tool_round(
                loop_messages, tool_calls_list, tools_by_name, tool_read_only,
                body.chat_id, final_asst_msg_id, variant_id, iter_collected,
            )

        full = "".join(collected)
        if body.continue_text and not full.startswith(body.continue_text):
            full = body.continue_text + full

        try:
            await _upsert_variant(
                body.chat_id,
                final_asst_msg_id,
                next_variant_index,
                full,
                body.regenerate,
                prov_dict.get("model", ""),
                variant_id=variant_id,
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

    collected: list[str] = []
    final_asst_msg_id = asst_msg_id

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
        yield f"data: {json.dumps({'type': 'start', 'message_id': final_asst_msg_id, 'user_message_id': user_msg_id if not body.regenerate else None, 'prefill_mode': not provider.echoes_prefill})}\n\n"

        loop_messages = list(messages)
        variant_saved = False
        final_text: list[str] = []
        stream_variant_id = str(uuid.uuid4())

        for _iteration in range(MAX_TOOL_ITERATIONS if tools_enabled else 1):
            iter_collected: list[str] = []
            tool_calls_list: list | None = None

            try:
                logger.debug(
                    "Stream iteration %d for chat_id=%s provider=%s",
                    _iteration + 1, body.chat_id, prov_dict["name"],
                )
                async for event in provider.stream_complete(loop_messages, **gen_kwargs):
                    if event["type"] == "token":
                        iter_collected.append(event["text"])
                        yield f"data: {json.dumps({'token': event['text']})}\n\n"
                        if len(iter_collected) % 5 == 0:
                            await _upsert_variant(
                                body.chat_id, final_asst_msg_id, next_variant_index,
                                "".join(iter_collected), body.regenerate, prov_dict.get("model", ""),
                                variant_id=stream_variant_id,
                            )
                    elif event["type"] == "tool_calls":
                        tool_calls_list = event["calls"]
                        yield f"data: {json.dumps({'type': 'tool_calls', 'calls': [{'id': tc.id, 'name': tc.name, 'arguments': tc.arguments} for tc in event['calls']]})}\n\n"
                        break
                    elif event["type"] == "done":
                        tool_calls_list = None
                        break
            except Exception as e:
                logger.exception("Stream exception for chat_id=%s", body.chat_id)
                logger.debug(
                    "stream: error state: iter_collected=%d final_text=%d regenerate=%s asst_msg_id=%s",
                    len(iter_collected), len(final_text), body.regenerate, final_asst_msg_id,
                )
                if iter_collected:
                    await _upsert_variant(
                        body.chat_id, final_asst_msg_id, next_variant_index,
                        "".join(iter_collected), body.regenerate, prov_dict.get("model", ""),
                        variant_id=stream_variant_id,
                    )
                elif not body.regenerate and not final_text:
                    await _rollback_assistant(final_asst_msg_id)
                err_msg = str(e)
                if not err_msg or err_msg == "()":
                    err_msg = repr(e)
                logger.info("Stream terminated (error) for chat_id=%s", body.chat_id)
                yield f"data: {json.dumps({'error': err_msg})}\n\n"
                return

            if not tool_calls_list:
                final_text.extend(iter_collected)
                break

            final_text.extend(iter_collected)
            final_text.append("%%%TOOL_BOUNDARY%%%")

            tool_calls_list = list(tool_calls_list)

            results = await _apply_tool_round(
                loop_messages, tool_calls_list, tools_by_name, tool_read_only,
                body.chat_id, final_asst_msg_id, stream_variant_id, iter_collected,
            )

            for r in results:
                yield f"data: {json.dumps({'type': 'tool_result', 'call_id': r.call_id, 'name': next((tc.name for tc in tool_calls_list if tc.id == r.call_id), ''), 'result': r.content, 'is_error': r.is_error})}\n\n"

        full = "".join(final_text)
        if body.continue_text and not full.startswith(body.continue_text):
            full = body.continue_text + full

        logger.debug(
            "stream: saving variant asst_msg_id=%s variant_index=%d full_length=%d",
            final_asst_msg_id, next_variant_index, len(full),
        )
        try:
            await _upsert_variant(
                body.chat_id, final_asst_msg_id, next_variant_index,
                full, body.regenerate, prov_dict.get("model", ""),
                variant_id=stream_variant_id,
            )
            variant_saved = True
            logger.debug("stream: variant saved successfully")
        except Exception as e:
            logger.exception("Failed to save stream result for chat_id=%s", body.chat_id)
            if not body.regenerate:
                await _rollback_assistant(final_asst_msg_id)
            err_msg = str(e) or repr(e)
            yield f"data: {json.dumps({'error': f'Generation succeeded but save failed: {err_msg}'})}\n\n"
            return

        yield f"data: {json.dumps({'done': True, 'message_id': final_asst_msg_id, 'variant_index': next_variant_index})}\n\n"
        logger.info("Stream completed for chat_id=%s variant_saved=%s", body.chat_id, variant_saved)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _apply_tool_round(
    loop_messages: list,
    tool_calls_list: list,
    tools_by_name: dict,
    read_only: bool,
    chat_id: str,
    asst_msg_id: str,
    variant_id: str,
    iter_collected: list[str],
) -> list:
    """Build assistant message with tool_calls, execute tools, append results
    to loop_messages. Returns the ToolResult list so callers can yield SSE events."""
    asst_text = strip_think_blocks("".join(iter_collected)).strip()
    asst_msg: dict = {"role": "assistant", "content": asst_text or None}
    asst_msg["tool_calls"] = [
        {"id": tc.id, "type": "function",
         "function": {"name": tc.name, "arguments": json.dumps(tc.arguments)}}
        for tc in tool_calls_list
    ]
    loop_messages.append(asst_msg)

    results = await _execute_tool_round(
        tool_calls_list, tools_by_name, read_only,
        chat_id, asst_msg_id, variant_id,
    )
    loop_messages.extend(to_provider_tool_results(results))
    for r in results:
        if r.extra_message is not None:
            loop_messages.append(r.extra_message)

    return results


async def _execute_tool_round(
    tool_calls_list: list,
    tools_by_name: dict,
    read_only: bool,
    chat_id: str,
    asst_msg_id: str,
    variant_id: str | None,
) -> list:
    """Execute a list of ToolCall objects and return ToolResult list.

    Also persists each call to the tool_calls table.
    """
    results: list = []

    for call in tool_calls_list:
        tool = tools_by_name.get(call.name)
        if tool is None or (read_only and tool.writes):
            msg = "tool unavailable in read-only mode" if read_only else f"unknown tool: {call.name}"
            result = ToolResult(call.id, msg, is_error=True)
            results.append(result)
            logger.warning("Tool call blocked: %s (%s)", call.name, msg)
            continue
        try:
            logger.debug("Executing tool: %s args=%s", call.name, call.arguments)
            output = tool.handler(**call.arguments)
            if hasattr(output, "__await__"):
                output = await output
            result = build_tool_result(call.id, call.name, output)
            results.append(result)
        except Exception as e:
            logger.exception("Tool execution failed: %s", call.name)
            results.append(ToolResult(call.id, f"error: {e}", is_error=True))

    # Persist to tool_calls table
    if results:
        save_now = now_iso()
        async with aiosqlite.connect(DB_PATH) as save_db:
            await save_db.execute("PRAGMA foreign_keys=ON")
            for call, result in zip(tool_calls_list, results):
                await save_db.execute(
                    """INSERT INTO tool_calls
                       (id, chat_id, message_id, variant_id, tool_name, arguments, result, is_error, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        chat_id,
                        asst_msg_id,
                        variant_id,
                        call.name,
                        json.dumps(call.arguments),
                        result.content,
                        int(result.is_error),
                        save_now,
                    ),
                )
            await save_db.commit()

    return results


async def _upsert_variant(
    chat_id: str,
    asst_msg_id: str,
    variant_index: int,
    content: str,
    regenerate: bool,
    model_name: str = "",
    variant_id: str | None = None,
) -> str:
    """Insert or update a message variant. If a variant with the same
    (message_id, variant_index) exists, updates it in-place. Otherwise inserts
    a new row and copies attachments from the previous active variant on
    regenerate. Returns the variant id."""
    save_now = now_iso()

    async with aiosqlite.connect(DB_PATH) as save_db:
        await save_db.execute("PRAGMA foreign_keys=ON")
        cur = await save_db.execute(
            "SELECT id FROM message_variants WHERE message_id = ? AND variant_index = ?",
            (asst_msg_id, variant_index),
        )
        existing = await cur.fetchone()

        if existing:
            vid = existing[0]
            await save_db.execute(
                "UPDATE message_variants SET content = ?, model_name = ?, created_at = ? WHERE id = ?",
                (content, model_name or None, save_now, vid),
            )
        else:
            vid = variant_id or str(uuid.uuid4())
            await save_db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at, model_name) VALUES (?, ?, ?, ?, ?, ?)",
                (vid, asst_msg_id, variant_index, content, save_now, model_name or None),
            )
            if regenerate and variant_index > 0:
                async with save_db.execute("SELECT active_index FROM messages WHERE id = ?", (asst_msg_id,)) as act:
                    row = await act.fetchone()
                if row:
                    async with save_db.execute(
                        "SELECT * FROM message_attachments WHERE variant_id = (SELECT id FROM message_variants WHERE message_id = ? AND variant_index = ?) ORDER BY created_at",
                        (asst_msg_id, row[0]),
                    ) as att_cur:
                        old_attachments = [dict(r) for r in await att_cur.fetchall()]
                    for att in old_attachments:
                        await save_db.execute(
                            "INSERT INTO message_attachments (id, chat_id, message_id, variant_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (str(uuid.uuid4()), chat_id, asst_msg_id, vid, att["file_path"], att["mime_type"], save_now),
                        )

        await save_db.execute(
            "UPDATE messages SET active_index = ? WHERE id = ?",
            (variant_index, asst_msg_id),
        )
        await save_db.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (save_now, chat_id))
        await save_db.commit()

    return vid


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
                    img_tokens = estimate_image_tokens(*dims) if dims else 250
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
