import asyncio
import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from starlette.background import BackgroundTask

import focus.crud as crud
import focus.db as db
from focus.core.database import get_db
from focus.core.media import tool_image_url
from focus.core.models import ChatCreate, MessageEdit
from focus.core.paths import ATTACHMENTS_DIR
from focus.core.retry import RetryConfig
from focus.core.summary import summary_config
from focus.core.utils import read_upload
from focus.extensions.triggers import schedule_trigger

logger = logging.getLogger("focus.routers.chats")

router = APIRouter()


@router.post("/", status_code=201)
@router.post("", status_code=201)
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
@router.get("")
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
        """SELECT mv.content, mv.variant_meta, mv.segments_json, mv.id as variant_id
           FROM messages m
           JOIN message_variants mv ON mv.message_id = m.id AND mv.variant_index = m.active_index
           WHERE m.id = ? AND m.chat_id = ?""",
        (message_id, chat_id),
    ) as cur:
        row = await cur.fetchone()
    if not row:
        raise HTTPException(404, "Message not found")
    row = dict(row)

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
    for tc_row in tool_calls_rows:
        tc = dict(tc_row)
        tool_calls.append({
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["tool_name"],
                "arguments": tc["arguments"],
            },
            "result": tc["result"],
            "is_error": bool(tc["is_error"]),
            "image_data": (
                tool_image_url(tc['result_image_path']) if tc.get("result_image_path")
                else None
            ),
        })

    try:
        vm = json.loads(row["variant_meta"]) if row.get("variant_meta") else {}
    except (TypeError, ValueError):
        vm = {}

    segments = None
    if row.get("segments_json"):
        try:
            segments = json.loads(row["segments_json"])
        except (TypeError, ValueError):
            segments = None

    return {
        "content": row["content"],
        "reasoning": vm.get("reasoning"),
        "attachments": attachments,
        "tool_calls": tool_calls,
        "segments": segments,
    }


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
        _db, chat_id, message_id, body.content, body.reasoning, body.attachment_ids, body.segments,
    )
    await _db.commit()
    # Fire-and-forget: auto-run extensions subscribed to the edit event.
    await schedule_trigger(_db, chat_id, "edit", message_id)
    return {"ok": True, **result}


@router.put("/{chat_id}/messages/{message_id}/pin")
async def pin_message(
    chat_id: str,
    message_id: str,
    body: MessagePin,
    _db=Depends(get_db),
):
    """Set a message's pin flag (user metadata; carried verbatim into forks)."""
    if not await db.set_message_pinned(_db, chat_id, message_id, body.pinned):
        raise HTTPException(404, "Message not found")
    await _db.commit()
    return {"pinned": body.pinned}


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
    # Fire-and-forget: auto-run extensions subscribed to the swipe event.
    await schedule_trigger(_db, chat_id, "swipe", message_id)
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


class SummarizeRequest(BaseModel):
    provider_id: str = ""
    message_id: str = ""


class MessagePin(BaseModel):
    pinned: bool


class SummaryChunkUpdate(BaseModel):
    id: str
    content: str


class SummaryUpdate(BaseModel):
    chunks: list[SummaryChunkUpdate]


async def _active_provider_id(_db) -> str:
    async with _db.execute("SELECT value FROM settings WHERE key = 'active_provider_id'") as cur:
        row = await cur.fetchone()
    return row["value"] if row else ""


# One in-flight summary per chat. The check-and-add is synchronous (no await
# between), so concurrent requests can't both start a fork. Maps chat_id to
# its stop event (set by the stop endpoint). The slot is released by the
# stream's finally and by the response background task — the latter covers a
# generator that is never started (instant disconnect), whose finally would
# otherwise never run and lock the chat out for good.
_active_summaries: dict[str, asyncio.Event] = {}

# Per-attempt ceiling for the buffered summary call; a hung provider request
# would otherwise block the request forever. Retries get their own window.
SUMMARY_ATTEMPT_TIMEOUT = 300.0


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.post("/{chat_id}/summarize")
async def summarize_chat(chat_id: str, body: SummarizeRequest, _db=Depends(get_db)):
    """Summarize *chat_id* in an ephemeral generation and fork a child chat.

    The summary turn is never persisted: it is assembled from the chat's normal
    context plus one instruction message, sent to the provider, and only the
    resulting text is stored (as a ``chat_summaries`` row). The child chat
    inherits that summary and the chat's recent messages as leading context.

    Streams SSE so transient provider failures can be retried transparently
    with the same feedback the normal generation path shows.
    """
    if chat_id in _active_summaries:
        raise HTTPException(409, "A summary is already being generated for this chat")
    stop_event = asyncio.Event()
    _active_summaries[chat_id] = stop_event

    def _release() -> None:
        if _active_summaries.get(chat_id) is stop_event:
            _active_summaries.pop(chat_id, None)

    try:
        prep = await _prepare_summary(_db, chat_id, body)
    except BaseException:
        _release()
        raise

    from focus.routers.stream import _error_reason, buffered_completion_with_retry

    chat = prep["chat"]

    async def events():
        try:
            yield _sse({"type": "start"})
            summary_text: str | None = None
            async for ev in buffered_completion_with_retry(
                prep["provider"], prep["messages"], prep["gen_kwargs"],
                prep["retry_config"], stop_event=stop_event,
                attempt_timeout=SUMMARY_ATTEMPT_TIMEOUT,
            ):
                if ev.get("stopped"):
                    yield _sse({"type": "done", "cancelled": True})
                    return
                if ev["type"] == "text":
                    summary_text = ev["text"]
                    continue
                yield _sse(ev)
                if ev["type"] == "error":
                    return
            if not summary_text:
                yield _sse({"type": "error", "error": "The provider returned an empty summary."})
                return
            try:
                summary_id = await db.create_summary(
                    _db, chat_id, summary_text, prep["covered_to_position"],
                    prep["prov_dict"].get("model"),
                )
                child_id = await db.create_chat(
                    _db,
                    character_id=chat.get("character_id"),
                    persona_id=chat.get("persona_id"),
                    preset_id=chat.get("preset_id"),
                    title=chat.get("title") or "New Chat",
                    parent_chat_id=chat_id,
                    summary_id=summary_id,
                )
                await _db.commit()
            except Exception as e:
                logger.exception("Failed to persist summary for chat_id=%s", chat_id)
                yield _sse({"type": "error", "error": f"Failed to save summary: {_error_reason(e)}"})
                return
            yield _sse({"type": "done", "id": child_id})
        finally:
            _release()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(_release),
    )


@router.post("/{chat_id}/summarize/stop")
async def stop_summary(chat_id: str):
    """Set the stop event for a running summary.

    The buffered provider call is cancelled in flight and the stream ends
    with a ``done``/``cancelled`` event — nothing is persisted.
    """
    stop_event = _active_summaries.get(chat_id)
    if stop_event is None:
        logger.warning("Stop requested for summary of chat_id=%s with none active", chat_id)
        raise HTTPException(404, "No active summary found")
    stop_event.set()
    logger.info("Stop requested for summary of chat_id=%s", chat_id)
    return {"ok": True}


@router.get("/{chat_id}/summary")
async def get_chat_summary(chat_id: str, _db=Depends(get_db)):
    """The summary chunks inherited by *chat_id*, oldest first."""
    chain = await db.get_chat_summary_chain(_db, chat_id)
    return {
        "chunks": [
            {
                "id": s["id"],
                "content": s["content"],
                "model_name": s.get("model_name"),
                "created_at": s.get("created_at"),
            }
            for s in chain
        ]
    }


@router.put("/{chat_id}/summary")
async def update_chat_summary(chat_id: str, body: SummaryUpdate, _db=Depends(get_db)):
    """Edit inherited summary chunks. A chunk must belong to this chat's chain."""
    chain = await db.get_chat_summary_chain(_db, chat_id)
    allowed = {s["id"] for s in chain}
    for chunk in body.chunks:
        if chunk.id not in allowed:
            raise HTTPException(404, "Summary chunk is not part of this chat")
        await db.update_summary_content(_db, chunk.id, chunk.content)
    await _db.commit()
    return {"ok": True}


async def _prepare_summary(_db, chat_id: str, body: SummarizeRequest) -> dict:
    """Validate a summarize request and assemble everything the stream needs."""
    async with _db.execute("SELECT * FROM chats WHERE id = ? AND is_deleted = 0", (chat_id,)) as cur:
        chat_row = await cur.fetchone()
    if not chat_row:
        raise HTTPException(404, "Chat not found")
    chat = dict(chat_row)

    preset_blocks: list[dict] = []
    preset_settings: str = "{}"
    if chat.get("preset_id"):
        async with _db.execute(
            "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid",
            (chat["preset_id"],),
        ) as cur:
            preset_blocks = [dict(r) for r in await cur.fetchall()]
        async with _db.execute(
            "SELECT settings_json FROM presets WHERE id = ?", (chat["preset_id"],)
        ) as cur:
            preset_row = await cur.fetchone()
        if preset_row and preset_row["settings_json"]:
            preset_settings = preset_row["settings_json"]
    cfg = summary_config(preset_blocks, preset_settings)
    if not cfg["active"]:
        raise HTTPException(400, "Summary is disabled for this preset")

    provider_id = cfg["provider_id"] or body.provider_id or await _active_provider_id(_db)
    if not provider_id:
        raise HTTPException(400, "No provider selected")

    # Summarize up to and including the chosen message; without one, the whole chat.
    if body.message_id:
        async with _db.execute(
            "SELECT position FROM messages WHERE id = ? AND chat_id = ?",
            (body.message_id, chat_id),
        ) as cur:
            msg_row = await cur.fetchone()
        if not msg_row:
            raise HTTPException(404, "Message not found")
        covered_to_position = msg_row["position"]
    else:
        async with _db.execute(
            "SELECT COALESCE(MAX(position), 0) FROM messages WHERE chat_id = ?", (chat_id,),
        ) as cur:
            covered_to_position = (await cur.fetchone())[0]

    from focus.core.models import StreamRequest
    from focus.routers.stream import _load_provider
    from focus.routers.stream_utils import get_prompt_context, prepare_generation_messages

    # A provider saved on the preset can dangle (deleted, or imported preset).
    try:
        provider, prov_dict = await _load_provider(_db, provider_id)
    except HTTPException:
        fallback = body.provider_id or await _active_provider_id(_db)
        if not fallback or fallback == provider_id:
            raise
        provider, prov_dict = await _load_provider(_db, fallback)

    ctx = await get_prompt_context(
        _db, chat_id, regenerate=False,
        user_message=cfg["instruction"], attachment_ids=[], persist=False,
        up_to_position=covered_to_position, summary_pass=True,
    )

    req_body = StreamRequest(chat_id=chat_id, provider_id=provider_id)
    messages, gen_kwargs = await prepare_generation_messages(
        prov_dict, req_body, ctx.messages, provider, chat_id,
    )
    gen_kwargs.pop("stream_enabled", None)
    gen_kwargs["stream"] = False
    if cfg["max_tokens"] > 0:
        gen_kwargs["max_tokens"] = cfg["max_tokens"]

    try:
        prov_config = json.loads(prov_dict.get("config_json") or "{}")
    except json.JSONDecodeError:
        prov_config = {}

    return {
        "chat": chat,
        "provider": provider,
        "prov_dict": prov_dict,
        "messages": messages,
        "gen_kwargs": gen_kwargs,
        "retry_config": RetryConfig.from_config(prov_config),
        "covered_to_position": covered_to_position,
    }


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
