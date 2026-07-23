import asyncio
import copy
import json
import logging
import sqlite3
import uuid
from collections.abc import AsyncIterator

import aiosqlite
import tiktoken
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from focus.core.database import DB_PATH, get_db
from focus.core.logger import get_logger
from focus.core.message_render import (
    _escape_html,
    _extract_think_blocks,
    strip_think_blocks,
)
from focus.core.models import ItemizerRequest, StreamRequest
from focus.core.utils import (
    AUDIO_TOKEN_ESTIMATE,
    _image_dims_from_data_url,
    estimate_image_tokens,
    now_iso,
    resolve_secret_key,
)
from focus.providers import create_provider
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
    extract_image_url,
)
from focus.tools.builtin import get_all_tools
from focus.tools.provider_adapter import to_provider_tools

router = APIRouter()
logger = get_logger("routers.stream")

# Track active streaming generations for graceful stop (message_id → Event)
_active_generations: dict[str, asyncio.Event] = {}



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



async def _prepare_generation_messages(
    prov_dict: dict,
    body: StreamRequest,
    messages: list[dict],
    provider,
    chat_id: str,
) -> tuple[list[dict], dict]:
    """Apply modality filtering, caching, field stripping, prefill,
    sampler processing, and OpenRouter sticky routing.
    Returns (filtered_messages, gen_kwargs)."""

    s = dict(body.samplers) if body.samplers else {}
    if s.pop("disable_multimodal", False):
        messages = filter_unsupported_modalities(messages, ["text"])

    if prov_dict.get("type") == "openrouter":
        modalities = await get_openrouter_model_modalities(prov_dict.get("model", ""))
        if modalities:
            messages = filter_unsupported_modalities(messages, modalities)

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

        # Preserve thinking: unified 3-way logic for all non-Google providers
        raw = (body.samplers or {}).get("preserve_thinking", False)
        if isinstance(raw, str):
            v = raw.lower()
            if v in ("all", "true"):
                mode = "all"
            elif v == "tool_only":
                mode = "tool_only"
            else:
                mode = "off"
        elif raw is True:
            mode = "all"
        else:
            mode = "off"

        if mode == "off":
            for msg in messages:
                if msg.get("role") == "assistant" and msg.get("reasoning"):
                    msg.pop("reasoning")
        elif mode == "tool_only":
            for msg in messages:
                if msg.get("role") == "assistant" and msg.get("reasoning") and not msg.get("tool_calls") and msg.get("content"):
                    msg.pop("reasoning")

    if (body.continue_text is not None or body.continue_reasoning) and body.regenerate and provider.supports_prefill:
        prefill_msg = {"role": "assistant", "content": body.continue_text or ""}
        if body.continue_reasoning:
            prefill_msg["reasoning"] = body.continue_reasoning
        messages.append(prefill_msg)

    gen_kwargs: dict = {}
    if body.samplers:
        s = dict(body.samplers)
        s.pop("disable_multimodal", None)
        s.pop("cache_enabled", None)
        s.pop("cache_ttl", None)
        s.pop("cache_depth", None)
        gen_kwargs.update(s)

    if prov_dict.get("type") == "openrouter":
        gen_kwargs["session_id"] = chat_id
    if prov_dict.get("type") == "moonshot":
        gen_kwargs["prompt_cache_key"] = chat_id

    return messages, gen_kwargs



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


def _prefill_reasoning(body: StreamRequest, messages: list[dict]) -> str | None:
    """Return the prefill reasoning text that the provider won't echo back.

    Checks body.continue_reasoning first (explicit continue/regenerate),
    then falls back to the last message if it's an assistant thinking-only
    block (reasoning with empty content).  Returns None if no such text.
    """
    if body.continue_reasoning:
        return body.continue_reasoning
    if messages and messages[-1].get("role") == "assistant" and messages[-1].get("reasoning"):
        return messages[-1]["reasoning"]
    return None



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
            err_msg = str(e)
            if not err_msg or err_msg == "()":
                err_msg = repr(e)
            yield {"type": "error", "error": err_msg}
            return

        if not tool_calls_list:
            yield {"type": "done"}
            return

        tool_calls_list = list(tool_calls_list)
        yield {"type": "tool_calls", "calls": tool_calls_list}

        logger.debug("Tool round (%d calls) for chat_id=%s", len(tool_calls_list), chat_id)

        try:
            results = await _apply_tool_round(
                loop_messages, tool_calls_list, tools_by_name, tool_read_only,
                chat_id, asst_msg_id, variant_id, iter_collected, iter_reasoning,
                disable_multimodal=disable_multimodal,
            )
        except Exception as e:
            logger.exception("Tool round failed for chat_id=%s", chat_id)
            err_msg = str(e)
            if not err_msg or err_msg == "()":
                err_msg = repr(e)
            yield {"type": "error", "error": err_msg}
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



async def _stream_generate(
    body: StreamRequest,
    provider,
    prov_dict: dict,
    messages: list[dict],
    gen_kwargs: dict,
    asst_msg_id: str,
    next_variant_index: int,
    user_msg_id: str | None,
    tools_enabled: bool,
    tools_by_name: dict,
    tool_read_only: bool,
    disable_multimodal: bool = False,
    stop_event: asyncio.Event | None = None,
) -> AsyncIterator[str]:
    """Async generator that yields SSE-encoded lines for a streaming response."""
    variant_id = str(uuid.uuid4())
    variant_saved = False
    final_text: list[str] = []
    final_reasoning: list[str] = []
    _text_slices: list[int] = []      # len(final_text) at each tool boundary
    _reasoning_slices: list[int] = [] # len(final_reasoning) at each tool boundary
    _tool_groups: list[list[dict]] = []  # per-boundary tool call dicts

    # start SSE
    start_data = json.dumps({
        'type': 'start',
        'message_id': asst_msg_id,
        'user_message_id': user_msg_id if not body.regenerate else None,
    })
    yield f"data: {start_data}\n\n"

    # core loop — GeneratorExit/CancelledError are caught here because aclose()
    # throws them at the SSE ``yield`` points below.
    try:
        # Emit prefill as synthetic events (inside try so GeneratorExit
        # from these yields is caught and cleanup runs).
        if not provider.echoes_prefill:
            pref_reasoning = _prefill_reasoning(body, messages)
            if pref_reasoning:
                final_reasoning.append(pref_reasoning)
                yield f"data: {json.dumps({'type': 'reasoning', 'text': pref_reasoning})}\n\n"
            if body.continue_text:
                final_text.append(body.continue_text)
                yield f"data: {json.dumps({'token': body.continue_text})}\n\n"

        async for event in _run_generation(
            provider, messages, gen_kwargs, tools_enabled,
            tools_by_name, tool_read_only, disable_multimodal,
            body.chat_id, asst_msg_id, variant_id,
            stop_event,
        ):
            if event["type"] == "token":
                final_text.append(event["text"])
                if len(final_text) % 5 == 0:
                    await _upsert_variant(
                        body.chat_id, asst_msg_id, next_variant_index,
                        "".join(final_text), body.regenerate, prov_dict.get("model", ""),
                        variant_id=variant_id,
                        reasoning="".join(final_reasoning).strip() or None,
                    )
                yield f"data: {json.dumps({'token': event['text']})}\n\n"

            elif event["type"] == "reasoning":
                final_reasoning.append(event["text"])
                # Save before yield — if aclose() throws GeneratorExit at
                # the yield below the reasoning is already committed.
                await _upsert_variant(
                    body.chat_id, asst_msg_id, next_variant_index,
                    "".join(final_text), body.regenerate, prov_dict.get("model", ""),
                    variant_id=variant_id,
                    reasoning="".join(final_reasoning).strip() or None,
                )
                yield f"data: {json.dumps({'type': 'reasoning', 'text': event['text']})}\n\n"

            elif event["type"] == "tool_calls":
                _text_slices.append(len(final_text))
                _reasoning_slices.append(len(final_reasoning))

                group_calls = [
                    {
                        'id': tc.id,
                        'type': 'function',
                        'function': {'name': tc.name, 'arguments': json.dumps(tc.arguments)},
                    }
                    for tc in event['calls']
                ]
                _tool_groups.append(group_calls)

                tc_data = json.dumps({
                    'type': 'tool_calls',
                    'calls': [
                        {'id': tc.id, 'name': tc.name, 'arguments': tc.arguments}
                        for tc in event['calls']
                    ],
                })
                yield f"data: {tc_data}\n\n"

            elif event["type"] == "tool_result":
                if _tool_groups:
                    for tc in _tool_groups[-1]:
                        if tc['id'] == event['call_id']:
                            tc['result'] = event['result']
                            tc['is_error'] = event['is_error']
                            tc['image_url'] = event.get('image_url') or None
                            break
                tr_data = json.dumps({
                    'type': 'tool_result',
                    'call_id': event['call_id'],
                    'name': event['name'],
                    'result': event['result'],
                    'is_error': event['is_error'],
                    'image_url': event.get('image_url') or None,
                })
                yield f"data: {tr_data}\n\n"

            elif event["type"] == "usage":
                await _save_usage(
                    body.chat_id, asst_msg_id, variant_id,
                    prov_dict.get("id"), prov_dict.get("type"),
                    prov_dict.get("model", ""),
                    event["usage"],
                    tool_iteration=len(_tool_groups),
                )

            elif event["type"] == "done":
                # save final variant — close final iteration boundary
                _text_slices.append(len(final_text))
                _reasoning_slices.append(len(final_reasoning))

                full = "".join(final_text)
                full_reasoning = "".join(final_reasoning).strip() or None

                segments = _build_segments(
                    _text_slices, _reasoning_slices,
                    final_text, final_reasoning,
                    tool_call_groups=_tool_groups if _tool_groups else None,
                )

                logger.debug(
                    "stream: saving variant asst_msg_id=%s variant_index=%d full_length=%d reasoning=%s segments=%d",
                    asst_msg_id, next_variant_index, len(full),
                    "yes" if full_reasoning else "no", len(segments),
                )
                try:
                    await _upsert_variant(
                        body.chat_id, asst_msg_id, next_variant_index,
                        full, body.regenerate, prov_dict.get("model", ""),
                        variant_id=variant_id, reasoning=full_reasoning,
                        segments_json=json.dumps(segments) if segments else None,
                    )
                    variant_saved = True
                    logger.debug("stream: variant saved successfully")
                except Exception as e:
                    logger.exception("Failed to save stream result for chat_id=%s", body.chat_id)
                    if not body.regenerate:
                        await _rollback_assistant(asst_msg_id)
                    err_msg = str(e) or repr(e)
                    yield f"data: {json.dumps({'error': f'Generation succeeded but save failed: {err_msg}'})}\n\n"
                    return

                done_data = json.dumps({
                    'done': True,
                    'message_id': asst_msg_id,
                    'variant_index': next_variant_index,
                })
                yield f"data: {done_data}\n\n"
                logger.info("Stream completed for chat_id=%s variant_saved=%s", body.chat_id, variant_saved)
                return

            elif event["type"] == "error":
                logger.debug(
                    "stream: error state: final_text=%d regenerate=%s asst_msg_id=%s",
                    len(final_text), body.regenerate, asst_msg_id,
                )
                _text_slices.append(len(final_text))
                _reasoning_slices.append(len(final_reasoning))
                segments = _build_segments(
                    _text_slices, _reasoning_slices,
                    final_text, final_reasoning,
                    tool_call_groups=_tool_groups if _tool_groups else None,
                )
                await _save_or_rollback(
                    body, asst_msg_id, next_variant_index, variant_id,
                    final_text, final_reasoning, prov_dict,
                    segments_json=json.dumps(segments) if segments else None,
                )
                yield f"data: {json.dumps({'error': event['error']})}\n\n"
                logger.info("Stream terminated (error) for chat_id=%s", body.chat_id)
                return
    except GeneratorExit:
        _text_slices.append(len(final_text))
        _reasoning_slices.append(len(final_reasoning))
        segments = _build_segments(
            _text_slices, _reasoning_slices,
            final_text, final_reasoning,
            tool_call_groups=_tool_groups if _tool_groups else None,
        )
        await _save_or_rollback(
            body, asst_msg_id, next_variant_index, variant_id,
            final_text, final_reasoning, prov_dict,
            segments_json=json.dumps(segments) if segments else None,
        )
        logger.info("Stream cancelled for chat_id=%s", body.chat_id)
        return
    except asyncio.CancelledError:
        _text_slices.append(len(final_text))
        _reasoning_slices.append(len(final_reasoning))
        segments = _build_segments(
            _text_slices, _reasoning_slices,
            final_text, final_reasoning,
            tool_call_groups=_tool_groups if _tool_groups else None,
        )
        await _save_or_rollback(
            body, asst_msg_id, next_variant_index, variant_id,
            final_text, final_reasoning, prov_dict,
            segments_json=json.dumps(segments) if segments else None,
        )
        raise
    finally:
        _active_generations.pop(asst_msg_id, None)



async def _non_stream_generate(
    body: StreamRequest,
    provider,
    prov_dict: dict,
    messages: list[dict],
    gen_kwargs: dict,
    asst_msg_id: str,
    next_variant_index: int,
    user_msg_id: str | None,
    tools_enabled: bool,
    tools_by_name: dict,
    tool_read_only: bool,
    disable_multimodal: bool = False,
) -> JSONResponse:
    """Run generation in non-streaming mode and return a JSON response."""
    collected: list[str] = []
    collected_reasoning: list[str] = []
    n_text_slices: list[int] = []
    n_reasoning_slices: list[int] = []
    n_tool_groups: list[list[dict]] = []
    variant_id = str(uuid.uuid4())

    try:
        async for event in _run_generation(
            provider, messages, gen_kwargs, tools_enabled,
            tools_by_name, tool_read_only, disable_multimodal,
            body.chat_id, asst_msg_id, variant_id,
        ):
            if event["type"] == "token":
                collected.append(event["text"])
            elif event["type"] == "reasoning":
                collected_reasoning.append(event["text"])
            elif event["type"] == "tool_calls":
                n_text_slices.append(len(collected))
                n_reasoning_slices.append(len(collected_reasoning))
                group_calls = [
                    {
                        'id': tc.id,
                        'type': 'function',
                        'function': {'name': tc.name, 'arguments': json.dumps(tc.arguments)},
                    }
                    for tc in event['calls']
                ]
                n_tool_groups.append(group_calls)
            elif event["type"] == "tool_result":
                if n_tool_groups:
                    for tc in n_tool_groups[-1]:
                        if tc['id'] == event['call_id']:
                            tc['result'] = event['result']
                            tc['is_error'] = event['is_error']
                            tc['image_url'] = event.get('image_url') or None
                            break
            elif event["type"] == "usage":
                await _save_usage(
                    body.chat_id, asst_msg_id, variant_id,
                    prov_dict.get("id"), prov_dict.get("type"),
                    prov_dict.get("model", ""),
                    event["usage"],
                    tool_iteration=len(n_tool_groups),
                )
            elif event["type"] == "error":
                n_text_slices.append(len(collected))
                n_reasoning_slices.append(len(collected_reasoning))
                segments = _build_segments(
                    n_text_slices, n_reasoning_slices,
                    collected, collected_reasoning,
                    tool_call_groups=n_tool_groups if n_tool_groups else None,
                )
                if collected or collected_reasoning:
                    await _upsert_variant(
                        body.chat_id, asst_msg_id, next_variant_index,
                        "".join(collected), body.regenerate, prov_dict.get("model", ""),
                        variant_id=variant_id,
                        reasoning="".join(collected_reasoning).strip() or None,
                        segments_json=json.dumps(segments) if segments else None,
                    )
                elif not body.regenerate:
                    await _rollback_assistant(asst_msg_id)
                raise HTTPException(500, event["error"])
    except asyncio.CancelledError:
        if collected or collected_reasoning:
            await _upsert_variant(
                body.chat_id, asst_msg_id, next_variant_index,
                "".join(collected), body.regenerate, prov_dict.get("model", ""),
                variant_id=variant_id,
                reasoning="".join(collected_reasoning).strip() or None,
            )
        elif not body.regenerate:
            await _rollback_assistant(asst_msg_id)
        raise HTTPException(499, "Request cancelled")

    # Close final iteration boundary
    n_text_slices.append(len(collected))
    n_reasoning_slices.append(len(collected_reasoning))

    # Apply prefill (insert at position 0) and adjust slice indices
    prefill_text_len = 0
    prefill_reasoning_len = 0
    if not provider.echoes_prefill:
        if body.continue_text:
            collected.insert(0, body.continue_text)
            prefill_text_len = 1
        pref_r = _prefill_reasoning(body, messages)
        if pref_r:
            collected_reasoning.insert(0, pref_r)
            prefill_reasoning_len = 1
    if prefill_text_len:
        n_text_slices = [s + prefill_text_len for s in n_text_slices]
    if prefill_reasoning_len:
        n_reasoning_slices = [s + prefill_reasoning_len for s in n_reasoning_slices]

    full = "".join(collected)
    full_reasoning = "".join(collected_reasoning).strip() or None

    segments = _build_segments(
        n_text_slices, n_reasoning_slices,
        collected, collected_reasoning,
        tool_call_groups=n_tool_groups if n_tool_groups else None,
    )

    try:
        await _upsert_variant(
            body.chat_id, asst_msg_id, next_variant_index,
            full, body.regenerate, prov_dict.get("model", ""),
            variant_id=variant_id, reasoning=full_reasoning,
            segments_json=json.dumps(segments) if segments else None,
        )
    except Exception as e:
        logger.exception("Failed to save non-stream result for chat_id=%s", body.chat_id)
        if not body.regenerate:
            await _rollback_assistant(asst_msg_id)
        raise HTTPException(500, f"Generation succeeded but save failed: {str(e) or repr(e)}")

    return JSONResponse({
        "done": True,
        "message_id": asst_msg_id,
        "variant_index": next_variant_index,
        "user_message_id": user_msg_id if not body.regenerate else None,
        "full_text": full,
        "full_reasoning": full_reasoning,
    })



async def _save_or_rollback(
    body: StreamRequest,
    asst_msg_id: str,
    variant_index: int,
    variant_id: str,
    final_text: list[str],
    final_reasoning: list[str],
    prov_dict: dict,
    segments_json: str | None = None,
) -> None:
    """On error or cancellation, save any partial text/reasoning or
    rollback the empty assistant slot so the DB stays consistent."""
    if final_text or final_reasoning:
        await _upsert_variant(
            body.chat_id, asst_msg_id, variant_index,
            "".join(final_text), body.regenerate, prov_dict.get("model", ""),
            variant_id=variant_id,
            reasoning="".join(final_reasoning).strip() or None,
            segments_json=segments_json,
        )
    elif not body.regenerate:
        await _rollback_assistant(asst_msg_id)


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

    # Register this generation for graceful stop
    stop_event = asyncio.Event()
    _active_generations[asst_msg_id] = stop_event

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

    messages, gen_kwargs = await _prepare_generation_messages(
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

    # Dispatch
    if not use_stream:
        return await _non_stream_generate(
            body, provider, prov_dict, messages, gen_kwargs,
            asst_msg_id, next_variant_index, user_msg_id,
            tools_enabled, tools_by_name, tool_read_only,
            disable_multimodal,
        )

    return StreamingResponse(
        _stream_generate(
            body, provider, prov_dict, messages, gen_kwargs,
            asst_msg_id, next_variant_index, user_msg_id,
            tools_enabled, tools_by_name, tool_read_only,
            disable_multimodal, stop_event,
        ),
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


async def _apply_tool_round(
    loop_messages: list,
    tool_calls_list: list,
    tools_by_name: dict,
    read_only: bool,
    chat_id: str,
    asst_msg_id: str,
    variant_id: str,
    iter_collected: list[str],
    iter_reasoning: list[str] | None = None,
    disable_multimodal: bool = False,
) -> list:
    """Build assistant message with tool_calls, execute tools, append results
    to loop_messages. Returns the ToolResult list so callers can yield SSE events."""
    asst_text = "".join(iter_collected).strip()
    asst_msg: dict = {"role": "assistant", "content": asst_text or None}
    if iter_reasoning:
        reasoning_text = "".join(iter_reasoning).strip()
        if reasoning_text:
            asst_msg["reasoning"] = reasoning_text
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
    for r in results:
        loop_messages.append({"role": "tool", "tool_call_id": r.call_id, "content": r.content})
        if r.extra_message is not None:
            em = r.extra_message
            if disable_multimodal:
                content = em.get("content", [])
                if isinstance(content, list):
                    content = [p for p in content if p.get("type") == "text"]
                    if len(content) == 1:
                        em = {"role": "user", "content": content[0].get("text", "")}
                    else:
                        em = {"role": "user", "content": content}
            loop_messages.append(em)

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
            result = build_tool_result(call.id, call.name, output, multimodal=tool.multimodal)
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
                extra_msg = json.dumps(result.extra_message) if result.extra_message else None
                await save_db.execute(
                    """INSERT INTO tool_calls
                       (id, chat_id, message_id, variant_id, tool_name, arguments, result, is_error, extra_message_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        chat_id,
                        asst_msg_id,
                        variant_id,
                        call.name,
                        json.dumps(call.arguments),
                        result.content,
                        int(result.is_error),
                        extra_msg,
                        save_now,
                    ),
                )
            await save_db.commit()

    return results



def _build_segments(
    text_slices: list[int],
    reasoning_slices: list[int],
    final_text: list[str],
    final_reasoning: list[str],
    tool_call_groups: list[list[dict]] | None = None,
) -> list[dict]:
    """Build segment list from per-iteration text/reasoning ranges.

    When tool_call_groups are provided, each ``tool_boundary`` segment
    carries its own ``tool_calls`` list so the template can render calls
    per iteration instead of dumping all calls at the first boundary.

    Returns a flat list of segment dicts matching
    ``render_message_segments()`` output format:
      {"type": "text", "content": str}
      {"type": "reasoning", "html": str, "index": int}
      {"type": "tool_boundary"}           (legacy, no tool_calls)
      {"type": "tool_boundary", "tool_calls": [...]}  (new)
    """
    segments: list[dict] = []
    think_idx = 0
    prev_t = 0
    prev_r = 0

    for i in range(len(text_slices)):
        t_end = text_slices[i]
        r_end = reasoning_slices[i]

        # Reasoning from the separate field (if any for this iteration)
        if r_end > prev_r:
            r_text = "".join(final_reasoning[prev_r:r_end]).strip()
            if r_text:
                segments.append({
                    "type": "reasoning",
                    "html": _escape_html(r_text),
                    "index": think_idx,
                })
                think_idx += 1

        if t_end > prev_t:
            t_text = "".join(final_text[prev_t:t_end])
            think_idx = _extract_think_blocks(t_text, think_idx, segments)
            clean = strip_think_blocks(t_text)
            if clean.strip():
                segments.append({"type": "text", "content": clean})

        # Tool boundary between iterations (except the last)
        if i < len(text_slices) - 1:
            seg: dict = {"type": "tool_boundary"}
            if tool_call_groups and i < len(tool_call_groups):
                seg["tool_calls"] = tool_call_groups[i]
            segments.append(seg)

        prev_t = t_end
        prev_r = r_end

    return segments



async def _upsert_variant(
    chat_id: str,
    asst_msg_id: str,
    variant_index: int,
    content: str,
    regenerate: bool,
    model_name: str = "",
    variant_id: str | None = None,
    reasoning: str | None = None,
    segments_json: str | None = None,
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
                "UPDATE message_variants SET content = ?, model_name = ?, created_at = ?, reasoning = ?, segments_json = ? WHERE id = ?",
                (content, model_name or None, save_now, reasoning, segments_json, vid),
            )
        else:
            vid = variant_id or str(uuid.uuid4())
            await save_db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at, model_name, reasoning, segments_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (vid, asst_msg_id, variant_index, content, save_now, model_name or None, reasoning, segments_json),
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

        if content or reasoning:
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


async def _save_usage(
    chat_id: str,
    message_id: str,
    variant_id: str,
    provider_id: str | None,
    provider_type: str | None,
    model_name: str | None,
    usage: dict,
    tool_iteration: int = 0,
) -> None:
    """Persist token/cache/cost usage from a single API call to generation_usage."""
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
        async with aiosqlite.connect(DB_PATH) as save_db:
            await save_db.execute("PRAGMA foreign_keys=ON")
            params = (
                row_id, chat_id, message_id, variant_id,
                provider_id, provider_type, model_name,
                prompt, completion, total,
                cached, usage.get("reasoning_tokens", 0),
                cost,
                cost_details_str,
                tool_iteration,
                now,
            )
            sql = """INSERT INTO generation_usage
                   (id, chat_id, message_id, variant_id, provider_id, provider_type,
                    model_name, prompt_tokens, completion_tokens, total_tokens,
                    cached_tokens, reasoning_tokens, cost, cost_details,
                    tool_iteration, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"""
            try:
                await save_db.execute(sql, params)
            except sqlite3.IntegrityError:
                # Variant row may not exist yet (usage event can arrive before
                # any token/reasoning triggered _upsert_variant). Retry without
                # the variant FK rather than killing the stream over telemetry.
                await save_db.execute(sql, (params[0], params[1], params[2], None) + params[4:])
            await save_db.commit()
    except Exception:
        logger.exception("Failed to persist generation_usage for message_id=%s", message_id)


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
