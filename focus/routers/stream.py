import asyncio
import copy
import json
import logging
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import aiosqlite
import tiktoken
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from focus.core.database import get_db
from focus.core.logger import get_logger
from focus.core.models import ItemizerRequest, StreamRequest
from focus.core.segments import build_segments
from focus.core.utils import (
    AUDIO_TOKEN_ESTIMATE,
    _image_dims_from_data_url,
    estimate_image_tokens,
    resolve_secret_key,
)
from focus.crud import rollback_assistant, save_usage, upsert_variant
from focus.providers import create_provider
from focus.routers.stream_utils import (
    get_prompt_context,
    prefill_reasoning,
    prepare_generation_messages,
)
from focus.tools import (
    MAX_TOOL_ITERATIONS,
    active_tools,
    extract_image_url,
)
from focus.tools.builtin import get_all_tools
from focus.tools.executor import apply_tool_round
from focus.tools.provider_adapter import to_provider_tools

router = APIRouter()
logger = get_logger("routers.stream")

# Track active streaming generations for graceful stop (message_id → Event)
_active_generations: dict[str, asyncio.Event] = {}


@dataclass
class _GenCtx:
    """Bundles all generation-scoped state so we don't thread 14 params."""
    body: StreamRequest
    provider: Any
    prov_dict: dict
    messages: list[dict]
    gen_kwargs: dict
    asst_msg_id: str
    next_variant_index: int
    user_msg_id: str | None
    tools_enabled: bool
    tools_by_name: dict
    tool_read_only: bool
    disable_multimodal: bool
    stop_event: asyncio.Event | None
    db: aiosqlite.Connection | None


class _SaveFailed(Exception):
    """Raised when the final variant save fails during a successful generation."""


async def _load_provider(
    db: aiosqlite.Connection, provider_id: str
) -> tuple:
    """Fetch provider row, resolve secrets, create provider instance.
    Returns (provider, prov_dict)."""
    async with db.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)) as cur:
        prov_row = await cur.fetchone()
    if not prov_row:
        raise HTTPException(404, "Provider not found")
    prov_dict = dict(prov_row)
    prov_dict["api_key"] = await resolve_secret_key(db, prov_dict.get("api_key") or "")
    provider = create_provider(prov_dict)
    return provider, prov_dict


def _log_outbound_payload(
    messages: list[dict],
    gen_kwargs: dict,
    prov_dict: dict,
) -> None:
    """Log the full outbound payload with base64 data truncated."""
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


def _format_error(e: Exception) -> str:
    """Return a non-empty string representation of an exception."""
    msg = str(e)
    if not msg or msg == "()":
        msg = repr(e)
    return msg


async def _run_generation(
    provider,
    messages: list[dict],
    gen_kwargs: dict,
    tools_enabled: bool,
    tools_by_name: dict,
    tool_read_only: bool,
    disable_multimodal: bool = False,
    chat_id: str = "",
    asst_msg_id: str = "",
    variant_id: str = "",
    stop_event: asyncio.Event | None = None,
    db: aiosqlite.Connection | None = None,
) -> AsyncIterator[dict]:
    """Run the tool-calling iteration loop.

    Yields structured event dicts:
      {"type": "token",       "text": str}
      {"type": "reasoning",   "text": str}
      {"type": "tool_calls",  "calls": [ToolCall, ...]}
      {"type": "tool_result", "call_id": str, "name": str,
                               "result": str, "is_error": bool}
      {"type": "done"}
      {"type": "error",       "error": str}

    GeneratorExit and CancelledError are deliberately not caught here;
    the caller (``_stream_generate`` or ``_non_stream_generate``) is
    responsible for cancellation cleanup since ``GeneratorExit`` is
    thrown at the outer generator's yield points.
    """
    loop_messages: list = list(messages)

    for _iteration in range(MAX_TOOL_ITERATIONS if tools_enabled else 1):
        if stop_event and stop_event.is_set():
            yield {"type": "done"}
            return
        # Strip internal metadata before sending to the provider
        for msg in loop_messages:
            msg.pop("internal", None)
        iter_collected: list[str] = []
        iter_reasoning: list[str] = []
        tool_calls_list: list | None = None

        try:
            async for event in provider.stream_complete(loop_messages, **gen_kwargs):
                if stop_event and stop_event.is_set():
                    yield {"type": "done"}
                    return
                if event["type"] == "token":
                    iter_collected.append(event["text"])
                    yield {"type": "token", "text": event["text"]}
                elif event["type"] == "reasoning":
                    iter_reasoning.append(event["text"])
                    yield {"type": "reasoning", "text": event["text"]}
                elif event["type"] == "usage":
                    yield {"type": "usage", "usage": event["usage"]}
                elif event["type"] == "tool_calls":
                    tool_calls_list = event["calls"]
                    break
                elif event["type"] == "done":
                    break
        except Exception as e:
            logger.exception("Completion failed for chat_id=%s", chat_id)
            yield {"type": "error", "error": _format_error(e)}
            return

        if not tool_calls_list:
            yield {"type": "done"}
            return

        tool_calls_list = list(tool_calls_list)
        yield {"type": "tool_calls", "calls": tool_calls_list}

        logger.debug("Tool round (%d calls) for chat_id=%s", len(tool_calls_list), chat_id)

        try:
            results = await apply_tool_round(
                loop_messages, tool_calls_list, tools_by_name, tool_read_only,
                chat_id, asst_msg_id, variant_id, iter_collected, iter_reasoning,
                disable_multimodal=disable_multimodal, db=db,
            )
        except Exception as e:
            logger.exception("Tool round failed for chat_id=%s", chat_id)
            yield {"type": "error", "error": _format_error(e)}
            return
        for r in results:
            yield {
                "type": "tool_result",
                "call_id": r.call_id,
                "name": next((tc.name for tc in tool_calls_list if tc.id == r.call_id), ""),
                "result": r.content,
                "is_error": r.is_error,
                "image_url": extract_image_url(r) or None,
            }



@dataclass
class _GenAccumulator:
    """Mutable state shared by both stream and non-stream generation paths.

    Tracks accumulated text, reasoning, slice boundaries at tool iterations,
    and tool-call groups so that ``build_segments()`` (from
    ``focus/core/segments.py``) can reconstruct the iteration-by-iteration
    rendering.
    """
    text: list[str] = field(default_factory=list)
    reasoning: list[str] = field(default_factory=list)
    text_slices: list[int] = field(default_factory=list)
    reasoning_slices: list[int] = field(default_factory=list)
    tool_groups: list[list[dict]] = field(default_factory=list)
    variant_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    finalized: bool = False

    def add_text(self, chunk: str) -> None:
        self.text.append(chunk)

    def add_reasoning(self, chunk: str) -> None:
        self.reasoning.append(chunk)

    def begin_tool_iteration(self, tool_calls: list) -> list[dict]:
        self.text_slices.append(len(self.text))
        self.reasoning_slices.append(len(self.reasoning))
        group = [
            {
                'id': tc.id,
                'type': 'function',
                'function': {'name': tc.name, 'arguments': json.dumps(tc.arguments)},
            }
            for tc in tool_calls
        ]
        self.tool_groups.append(group)
        return group

    def update_tool_result(
        self, call_id: str, result: str, is_error: bool, image_url: str | None = None,
    ) -> None:
        if self.tool_groups:
            for tc in self.tool_groups[-1]:
                if tc['id'] == call_id:
                    tc['result'] = result
                    tc['is_error'] = is_error
                    tc['image_url'] = image_url or None
                    break

    def close_iteration(self) -> None:
        self.text_slices.append(len(self.text))
        self.reasoning_slices.append(len(self.reasoning))

    def build_segments(self) -> list[dict]:
        return build_segments(
            self.text_slices, self.reasoning_slices,
            self.text, self.reasoning,
            tool_call_groups=self.tool_groups if self.tool_groups else None,
        )

    def full_text(self) -> str:
        return "".join(self.text)

    def full_reasoning(self) -> str | None:
        r = "".join(self.reasoning).strip()
        return r or None


async def _run_generation_with_prefill(
    ctx: _GenCtx, variant_id: str
) -> AsyncIterator[dict]:
    """Emit prefill events if provider doesn't echo them, then delegate to ``_run_generation``."""
    if not ctx.provider.echoes_prefill:
        pref_r = prefill_reasoning(ctx.body, ctx.messages)
        if pref_r:
            yield {"type": "reasoning", "text": pref_r}
        if ctx.body.continue_text:
            yield {"type": "token", "text": ctx.body.continue_text}

    async for event in _run_generation(
        ctx.provider, ctx.messages, ctx.gen_kwargs, ctx.tools_enabled,
        ctx.tools_by_name, ctx.tool_read_only, ctx.disable_multimodal,
        ctx.body.chat_id, ctx.asst_msg_id, variant_id,
        stop_event=ctx.stop_event, db=ctx.db,
    ):
        yield event


async def _finalize_gen(ctx: _GenCtx, acc: _GenAccumulator, *, success: bool = False) -> None:
    """Idempotent final save. Persists variant or rolls back the empty assistant slot."""
    if acc.finalized:
        return
    acc.finalized = True
    acc.close_iteration()
    segments = acc.build_segments()
    has_content = bool(acc.full_text() or acc.full_reasoning())

    if not success and not has_content:
        if not ctx.body.regenerate:
            await rollback_assistant(ctx.asst_msg_id, db=ctx.db)
        return

    try:
        await upsert_variant(
            ctx.body.chat_id, ctx.asst_msg_id, ctx.next_variant_index,
            acc.full_text(), ctx.body.regenerate, ctx.prov_dict.get("model", ""),
            variant_id=acc.variant_id, reasoning=acc.full_reasoning(),
            segments_json=json.dumps(segments) if segments else None,
            db=ctx.db,
        )
    except Exception as e:
        logger.exception("Failed to save variant for message_id=%s", ctx.asst_msg_id)
        if not ctx.body.regenerate:
            await rollback_assistant(ctx.asst_msg_id, db=ctx.db)
        if success:
            raise _SaveFailed(e) from e


async def _handle_event(
    acc: _GenAccumulator, event: dict, ctx: _GenCtx
) -> dict | None:
    """Reduce one event from ``_run_generation``.

    Accumulates into *acc*, checkpoints to DB, returns the SSE payload
    the transport should send (``None`` for internal-only events like usage).
    """
    t = event["type"]

    if t == "token":
        acc.add_text(event["text"])
        if len(acc.text) % 5 == 0:
            await upsert_variant(
                ctx.body.chat_id, ctx.asst_msg_id, ctx.next_variant_index,
                acc.full_text(), ctx.body.regenerate, ctx.prov_dict.get("model", ""),
                variant_id=acc.variant_id, reasoning=acc.full_reasoning(),
                db=ctx.db,
            )
        return {"token": event["text"]}

    if t == "reasoning":
        acc.add_reasoning(event["text"])
        if len(acc.reasoning) % 5 == 0:
            await upsert_variant(
                ctx.body.chat_id, ctx.asst_msg_id, ctx.next_variant_index,
                acc.full_text(), ctx.body.regenerate, ctx.prov_dict.get("model", ""),
                variant_id=acc.variant_id, reasoning=acc.full_reasoning(),
                db=ctx.db,
            )
        return {"type": "reasoning", "text": event["text"]}

    if t == "tool_calls":
        acc.begin_tool_iteration(event["calls"])
        await upsert_variant(
            ctx.body.chat_id, ctx.asst_msg_id, ctx.next_variant_index,
            acc.full_text(), ctx.body.regenerate, ctx.prov_dict.get("model", ""),
            variant_id=acc.variant_id, reasoning=acc.full_reasoning(),
            db=ctx.db,
        )
        return {
            "type": "tool_calls",
            "calls": [
                {"id": c.id, "name": c.name, "arguments": c.arguments}
                for c in event["calls"]
            ],
        }

    if t == "tool_result":
        acc.update_tool_result(
            event["call_id"], event["result"],
            event["is_error"], event.get("image_url"),
        )
        return {
            "type": "tool_result",
            "call_id": event["call_id"],
            "name": event["name"],
            "result": event["result"],
            "is_error": event["is_error"],
            "image_url": event.get("image_url") or None,
        }

    if t == "usage":
        await save_usage(
            ctx.body.chat_id, ctx.asst_msg_id, acc.variant_id,
            ctx.prov_dict.get("id"), ctx.prov_dict.get("type"),
            ctx.prov_dict.get("model", ""),
            event["usage"],
            tool_iteration=len(acc.tool_groups), db=ctx.db,
        )
        return None

    if t == "done":
        await _finalize_gen(ctx, acc, success=True)
        return {
            "done": True,
            "message_id": ctx.asst_msg_id,
            "variant_index": ctx.next_variant_index,
        }

    if t == "error":
        await _finalize_gen(ctx, acc)
        return {"error": event["error"]}

    return None


async def _stream_generate(ctx: _GenCtx) -> AsyncIterator[str]:
    """Async generator that yields SSE-encoded lines for a streaming response."""
    acc = _GenAccumulator()

    _active_generations[ctx.asst_msg_id] = ctx.stop_event or asyncio.Event()

    yield f"data: {json.dumps({'type': 'start', 'message_id': ctx.asst_msg_id, 'user_message_id': None if ctx.body.regenerate else ctx.user_msg_id})}\n\n"

    try:
        async for event in _run_generation_with_prefill(ctx, acc.variant_id):
            payload = await _handle_event(acc, event, ctx)
            if payload is not None:
                yield f"data: {json.dumps(payload)}\n\n"
            if event["type"] in ("done", "error"):
                return
    except _SaveFailed as e:
        yield f"data: {json.dumps({'error': f'Generation succeeded but save failed: {_format_error(e)}'})}\n\n"
    except GeneratorExit:
        await _finalize_gen(ctx, acc)
    except asyncio.CancelledError:
        await _finalize_gen(ctx, acc)
        raise
    finally:
        _active_generations.pop(ctx.asst_msg_id, None)



async def _non_stream_generate(ctx: _GenCtx) -> JSONResponse:
    """Run generation in non-streaming mode and return a JSON response."""
    acc = _GenAccumulator()

    _active_generations[ctx.asst_msg_id] = ctx.stop_event or asyncio.Event()
    try:
        async for event in _run_generation_with_prefill(ctx, acc.variant_id):
            await _handle_event(acc, event, ctx)
            if event["type"] == "error":
                raise HTTPException(500, event["error"])
    except _SaveFailed as e:
        raise HTTPException(500, f"Generation succeeded but save failed: {_format_error(e)}")
    except asyncio.CancelledError:
        await _finalize_gen(ctx, acc)
        raise HTTPException(499, "Request cancelled")
    else:
        return JSONResponse({
            "done": True,
            "message_id": ctx.asst_msg_id,
            "variant_index": ctx.next_variant_index,
            "user_message_id": None if ctx.body.regenerate else ctx.user_msg_id,
            "full_text": acc.full_text(),
            "full_reasoning": acc.full_reasoning(),
        })
    finally:
        _active_generations.pop(ctx.asst_msg_id, None)


@router.post("/stream")
async def stream(body: StreamRequest, db: aiosqlite.Connection = Depends(get_db)):
    """Generate a streaming completion from the selected provider.

    Loads the provider config, resolves secrets, builds the prompt context,
    streams tokens via SSE, and persists the result as a message variant.
    Supports an iterative tool-calling loop when tools_enabled=True.
    """
    provider, prov_dict = await _load_provider(db, body.provider_id)

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

    # Generation-scoped event; registration is handled by _stream_generate / _non_stream_generate
    stop_event = asyncio.Event()

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

    messages, gen_kwargs = await prepare_generation_messages(
        prov_dict, body, messages, provider, body.chat_id,
    )

    use_stream = gen_kwargs.pop("stream_enabled", True)

    # Tool calling setup
    tools_enabled = body.tools_enabled
    tool_read_only = body.tool_read_only
    disable_multimodal = (body.samplers or {}).get("disable_multimodal", False)

    if tools_enabled and not provider.supports_tools:
        tools_enabled = False
        logger.debug("Tools disabled: provider %s does not support tool calling", prov_dict.get("type"))


    tools_by_name: dict = {}
    if tools_enabled:
        async with db.execute(
            "SELECT tool_name FROM chat_tool_states WHERE chat_id = ? AND enabled = 0", (body.chat_id,)
        ) as cur:
            disabled_tools = {row["tool_name"] for row in await cur.fetchall()}
        cur_tools = active_tools(
            get_all_tools(), tool_read_only,
            disable_multimodal=disable_multimodal,
            disabled_names=disabled_tools,
        )
        tools_payload = to_provider_tools(cur_tools)
        tools_by_name = {t.name: t for t in cur_tools}
        if tools_payload:
            gen_kwargs["tools"] = tools_payload
            gen_kwargs["tool_choice"] = "auto"

    # Debug log
    if logger.isEnabledFor(logging.DEBUG):
        _log_outbound_payload(messages, gen_kwargs, prov_dict)

    gctx = _GenCtx(
        body=body, provider=provider, prov_dict=prov_dict,
        messages=messages, gen_kwargs=gen_kwargs,
        asst_msg_id=asst_msg_id, next_variant_index=next_variant_index,
        user_msg_id=user_msg_id, tools_enabled=tools_enabled,
        tools_by_name=tools_by_name, tool_read_only=tool_read_only,
        disable_multimodal=disable_multimodal, stop_event=stop_event, db=db,
    )

    # Dispatch
    if not use_stream:
        return await _non_stream_generate(gctx)

    return StreamingResponse(
        _stream_generate(gctx),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/stop-generation/{message_id}")
async def stop_generation(message_id: str):
    """Set the stop event for an active generation.

    The SSE generator checks this event between tokens and drains gracefully,
    sending a ``done`` event so the frontend's read loop completes normally.
    """
    event = _active_generations.get(message_id)
    if not event:
        logger.warning("Stop requested for unknown message_id=%s", message_id)
        raise HTTPException(404, "No active generation found")
    event.set()
    logger.info("Graceful stop requested for message_id=%s", message_id)
    return {"ok": True}


@router.post("/itemize")
async def itemize_prompt(body: ItemizerRequest, db: aiosqlite.Connection = Depends(get_db)):
    ctx = await get_prompt_context(
        db, body.chat_id, body.regenerate, body.user_message, body.attachment_ids, persist=False
    )
    messages = ctx["messages"]

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

        if msg.get("reasoning"):
            r_tokens = len(enc.encode(msg["reasoning"]))
            tokens += r_tokens
            clean_parts.append({"type": "reasoning", "text": msg["reasoning"], "tokens": r_tokens})

        if msg.get("internal") and clean_messages:
            clean_messages[-1]["parts"].extend(clean_parts)
            clean_messages[-1]["tokens"] += tokens
        else:
            clean_messages.append({"role": role, "parts": clean_parts, "tokens": tokens})
        total_tokens += tokens

    return JSONResponse({"total_tokens": total_tokens, "messages": clean_messages})
