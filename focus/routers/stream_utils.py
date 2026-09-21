import asyncio
import html
import json
import logging
from dataclasses import dataclass
from typing import Any

import aiosqlite
from fastapi import HTTPException

import focus.crud as crud
from focus.core.card_parser import safe_load_card
from focus.core.macros import build_base_macros
from focus.core.tracked_fields import attach_to_message
from focus.core.models import StreamRequest
from focus.db.chats import (
    bind_attachments_to_message,
    create_message,
    create_message_with_variant,
)
from focus.core.media import tool_image_data_url
from focus.prompt_chain import assemble_prompt, build_content
from focus.routers.providers import get_openrouter_model_modalities
from focus.providers.quirks import apply_request_quirks


@dataclass
class PromptCtx:
    """Typed result of prompt assembly.  Single carrier through the chain."""
    messages: list[dict]
    asst_msg_id: str | None
    next_variant_index: int
    user_msg_id: str | None

logger = logging.getLogger("focus.routers.stream_utils")

_chat_locks: dict[str, asyncio.Lock] = {}
_chat_locks_creation_lock = asyncio.Lock()


async def _make_assistant_slot(db: aiosqlite.Connection, chat_id: str) -> str:
    """Insert a new assistant message row and return its id."""
    asst_id = await create_message(db, chat_id, "assistant")
    await db.commit()
    return asst_id


async def _last_active_role(db: aiosqlite.Connection, chat_id: str) -> str | None:
    """Role of the last message that has an active variant.

    Joined on the active variant so stranded assistant rows (created but never
    saved) cannot masquerade as the last turn.
    """
    async with db.execute(
        "SELECT m.role FROM messages m"
        " JOIN message_variants mv ON mv.message_id = m.id AND mv.variant_index = m.active_index"
        " WHERE m.chat_id = ? ORDER BY m.position DESC LIMIT 1",
        (chat_id,),
    ) as cur:
        row = await cur.fetchone()
    return row["role"] if row else None


async def _get_history(db: aiosqlite.Connection, chat_id: str, regenerate: bool):
    """Load message history and message attachments for a chat.

    Also loads tool_calls and attaches them to assistant messages that
    triggered them, inserting synthetic tool-role messages afterwards.
    """
    msg_attachments: dict[str, list[dict]] = {}
    async with db.execute(
        "SELECT * FROM message_attachments WHERE chat_id = ? AND variant_id IS NOT NULL ORDER BY created_at",
        (chat_id,),
    ) as cur:
        for r in await cur.fetchall():
            msg_attachments.setdefault(r["variant_id"], []).append(dict(r))

    # Load all tool_calls for this chat, grouped by variant_id
    tool_calls_by_variant: dict[str, list[dict]] = {}
    async with db.execute(
        "SELECT * FROM tool_calls WHERE chat_id = ? AND variant_id IS NOT NULL ORDER BY created_at",
        (chat_id,),
    ) as cur:
        for tc in await cur.fetchall():
            tool_calls_by_variant.setdefault(tc["variant_id"], []).append(dict(tc))

    if regenerate:
        all_rows = await crud.fetch_active_variants(db, chat_id)

        last_asst_id = None
        last_asst_variant_count = 0
        for r in reversed(all_rows):
            if r["role"] == "assistant" and r["position"] > 0:
                last_asst_id = r["id"]
                last_asst_variant_count = r["variant_count"]
                break

        history = []
        for r in all_rows:
            if r["id"] != last_asst_id:
                await _append_history_with_tool_calls(
                    history, r, msg_attachments, tool_calls_by_variant,
                )
        return history, last_asst_id, last_asst_variant_count
    else:
        history_rows = await crud.fetch_active_variants(db, chat_id)
        history = []
        for r in history_rows:
            await _append_history_with_tool_calls(
                history, r, msg_attachments, tool_calls_by_variant,
            )
        return history, None, 0


async def _append_history_with_tool_calls(
    history: list,
    row: dict,
    msg_attachments: dict,
    tool_calls_by_variant: dict,
):
    """Append a history entry for *row*, potentially followed by synthetic
    tool-role messages if the original assistant message had tool_calls."""
    content_text = row["content"].strip()

    # Attach tool_calls if this assistant message had them (keyed by variant_id)
    tcs = tool_calls_by_variant.get(row["variant_id"], [])

    # Parse variant_meta once
    variant_meta: dict[str, Any] = {}
    if row.get("variant_meta"):
        try:
            variant_meta = json.loads(row["variant_meta"])
        except (TypeError, ValueError):
            pass

    # Split path: when segments carry per-iteration tool boundaries, rebuild
    # the exact generation order (assistant text -> tool_calls -> tool results
    # -> extra user messages -> assistant reaction) instead of merging all
    # iterations into one assistant entry.
    if tcs and row["role"] == "assistant":
        segments = None
        if row.get("segments_json"):
            try:
                segments = json.loads(row["segments_json"])
            except (TypeError, ValueError):
                segments = None
        if segments and any(
            s.get("type") == "tool_boundary" and s.get("tool_calls") for s in segments
        ):
            await _append_segmented_tool_history(
                history, segments, tcs, variant_meta=variant_meta, model_name=row.get("model_name")
            )
            return

    content = await build_content(content_text, msg_attachments.get(row["variant_id"], []))

    entry: dict = {
        "role": row["role"],
        "content": content,
    }
    if row["role"] == "assistant":
        attach_to_message(entry, variant_meta)
        entry["_src_model"] = row.get("model_name")

    if tcs and row["role"] == "assistant":
        entry["tool_calls"] = [_tool_calls_payload(tc) for tc in tcs]

    history.append(entry)

    # Insert synthetic tool-role messages after the assistant message,
    # interleaved with any extra_message user messages (e.g. images)
    for tc in tcs:
        await _append_tool_messages(history, tc)


def _tool_calls_payload(tc: dict) -> dict:
    return {
        "id": tc["id"],
        "type": "function",
        "function": {
            "name": tc["tool_name"],
            "arguments": tc["arguments"],
        },
    }


async def _append_tool_messages(history: list, tc: dict) -> None:
    """Append a synthetic tool-role message for *tc*, followed by its
    extra_message user message (e.g. a tool-returned image) if present."""
    history.append({
        "role": "tool",
        "tool_call_id": tc["id"],
        "content": tc["result"] or "",
    })
    if tc.get("result_image_path"):
        data_url = await tool_image_data_url(tc["result_image_path"])
        if data_url:
            name = tc.get("tool_name", "tool")
            history.append({
                "role": "user",
                "content": [
                    {"type": "text", "text": f"<{name}>"},
                    {"type": "image_url", "image_url": {"url": data_url}},
                    {"type": "text", "text": f"</{name}>"},
                ],
                "internal": True,
            })
    elif tc.get("extra_message_json"):
        history.append(json.loads(tc["extra_message_json"]))


async def _append_segmented_tool_history(
    history: list, segments: list, tcs: list, variant_meta: dict | None = None, model_name: str | None = None
) -> None:
    """Rebuild per-iteration history from stored segments.

    Each ``tool_boundary`` segment with ``tool_calls`` closes an assistant
    chunk; the final chunk (the post-tool reaction) becomes a plain assistant
    entry. Reasoning segments store escaped HTML — unescaped here, which is
    the exact inverse of ``_escape_html`` in message_render.py.

    Segment calls carry the *provider* call id while ``tool_calls`` rows use
    a local uuid as PK, so calls are matched to rows by consumption order
    (boundaries are in generation order; rows are loaded ``ORDER BY
    created_at``), validated by tool name.

    When *variant_meta* is provided, tracked fields are attached only to the
    first assistant entry (the one carrying the initial tool calls) so each
    turn retains its own unique reasoning signature and preserve_thinking
    filtering doesn't strip it.
    """
    ordered = list(tcs)  # already ORDER BY created_at from _get_history
    pos = 0
    text_parts: list[str] = []
    reasoning_parts: list[str] = []
    meta_attached = False

    async def flush(group: list | None) -> None:
        nonlocal meta_attached
        text = "".join(text_parts).strip()
        reasoning = "".join(reasoning_parts).strip()
        if not text and not reasoning and not group:
            return
        entry: dict = {"role": "assistant", "content": text}
        if reasoning:
            entry["reasoning"] = reasoning
        if variant_meta and not meta_attached:
            attach_to_message(entry, variant_meta)
            entry["_src_model"] = model_name
            meta_attached = True
        if group:
            entry["tool_calls"] = [_tool_calls_payload(tc) for tc in group]
        history.append(entry)
        for tc in group or []:
            await _append_tool_messages(history, tc)
        text_parts.clear()
        reasoning_parts.clear()

    for seg in segments:
        seg_type = seg.get("type")
        if seg_type == "text":
            text_parts.append(seg.get("content", ""))
        elif seg_type == "reasoning":
            reasoning_parts.append(html.unescape(seg.get("html", "")))
        elif seg_type == "tool_boundary" and seg.get("tool_calls"):
            calls = seg["tool_calls"]
            group = ordered[pos:pos + len(calls)]
            pos += len(group)
            for call, tc in zip(calls, group):
                seg_name = (call.get("function") or {}).get("name")
                if seg_name and seg_name != tc["tool_name"]:
                    logger.warning(
                        "tool_calls/segment mismatch: segment %s vs row %s — order drift?",
                        seg_name, tc["tool_name"],
                    )
            await flush(group)
    await flush(None)


async def get_prompt_context(
    db: aiosqlite.Connection,
    chat_id: str,
    regenerate: bool,
    user_message: str,
    attachment_ids: list[str],
    persist: bool = False,
) -> PromptCtx:
    """Load chat state and assemble the full prompt context for generation.

    Validates the chat, loads character/persona/preset data, builds macros,
    fetches message history, persists the user message (when persist=True),
    loads block images for all relevant blocks, and assembles the final
    message list via assemble_prompt().

    Returns a PromptCtx with assembled messages and history metadata.
    """
    logger.debug(
        "get_prompt_context: chat_id=%s regenerate=%s user_message=%r attachment_ids=%s persist=%s",
        chat_id, regenerate, user_message, attachment_ids, persist,
    )
    async with db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)) as cur:
        chat = await cur.fetchone()
    if not chat:
        raise HTTPException(404, "Chat not found")
    chat = dict(chat)

    char_data: dict = {
        "name": "Assistant",
        "description": "",
        "personality": "",
        "scenario": "",
        "mes_example": "",
        "first_mes": "",
    }
    char_own_blocks: list[dict] = []

    if chat["character_id"]:
        char_data["id"] = chat["character_id"]
        async with db.execute("SELECT card_json FROM characters WHERE id = ?", (chat["character_id"],)) as cur:
            char_row = await cur.fetchone()
        if char_row:
            card_json = safe_load_card(char_row) or {}
            char_data.update(card_json)

        async with db.execute(
            "SELECT * FROM char_blocks WHERE character_id = ? ORDER BY position, rowid",
            (chat["character_id"],),
        ) as cur:
            char_own_blocks = [dict(r) for r in await cur.fetchall()]

    persona: dict | None = None
    if chat["persona_id"]:
        async with db.execute("SELECT * FROM personas WHERE id = ?", (chat["persona_id"],)) as cur:
            row = await cur.fetchone()
            if row:
                persona = dict(row)
    if not persona:
        async with db.execute("SELECT * FROM personas ORDER BY created_at LIMIT 1") as cur:
            row = await cur.fetchone()
            if row:
                persona = dict(row)

    macros = build_base_macros(char_data, persona)
    macros["_chat_id"] = chat_id

    preset_blocks: list[dict] = []
    if chat["preset_id"]:
        async with db.execute(
            "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid",
            (chat["preset_id"],),
        ) as cur:
            preset_blocks = [dict(r) for r in await cur.fetchall()]

    history, asst_msg_id, next_variant_index = await _get_history(db, chat_id, regenerate)
    logger.debug(
        "get_prompt_context: history loaded: %d messages, asst_msg_id=%s, next_variant_index=%d",
        len(history), asst_msg_id, next_variant_index,
    )

    # If regenerate was requested but there's no non-greeting assistant to
    # target (e.g. after a failed first message was rolled back), create a
    # fresh slot so the response has a home without corrupting the greeting.
    if regenerate and asst_msg_id is None and persist:
        asst_msg_id = await _make_assistant_slot(db, chat_id)
        next_variant_index = 0

    # An empty send means "reply to the pending user turn". With an assistant
    # turn last there is nothing to reply to, so refuse instead of stacking a
    # second assistant message.
    if persist and not regenerate and not (user_message.strip() or attachment_ids):
        if await _last_active_role(db, chat_id) != "user":
            raise HTTPException(400, "Nothing to reply to")

    user_msg_id = None
    if not regenerate:
        if persist:
            async with _chat_locks_creation_lock:
                if chat_id not in _chat_locks:
                    _chat_locks[chat_id] = asyncio.Lock()
            lock = _chat_locks[chat_id]
            async with lock:
                async with db.execute("SELECT MAX(position) FROM messages WHERE chat_id = ?", (chat_id,)) as cur:
                    pos_row = await cur.fetchone()
                next_pos = (pos_row[0] if pos_row[0] is not None else -1) + 1

                # Only create a user message if there's actual text or attachments
                if user_message.strip() or attachment_ids:
                    user_msg_id, user_variant_id = await create_message_with_variant(
                        db, chat_id, "user", user_message, position=next_pos,
                    )

                    logger.debug(
                        "get_prompt_context: created user msg id=%s variant_id=%s next_pos=%d",
                        user_msg_id, user_variant_id, next_pos,
                    )

                    # Bind any attached files to the newly created user message
                    if attachment_ids:
                        await bind_attachments_to_message(db, chat_id, user_msg_id, user_variant_id, attachment_ids)

                        placeholders = ",".join("?" * len(attachment_ids))
                        async with db.execute(
                            f"SELECT * FROM message_attachments WHERE id IN ({placeholders}) ORDER BY created_at",
                            attachment_ids,
                        ) as cur:
                            new_attachments = [dict(r) for r in await cur.fetchall()]
                        logger.debug(
                            "get_prompt_context: bound %d attachments to user msg, fetched %d attachment rows",
                            len(attachment_ids), len(new_attachments),
                        )
                    else:
                        new_attachments = []

                    history.append({"role": "user", "content": await build_content(user_message, new_attachments)})
                    logger.debug(
                        "get_prompt_context: appended user msg to history, history now has %d messages",
                        len(history),
                    )
                    next_pos += 1

                    # Create assistant message slot
                asst_msg_id = await _make_assistant_slot(db, chat_id)
                logger.debug(
                    "get_prompt_context: created assistant slot id=%s",
                    asst_msg_id,
                )
                next_variant_index = 0
        else:
            # Read-only path (itemizer): just append to history in memory
            if user_message.strip() or attachment_ids:
                new_attachments = []
                if attachment_ids:
                    placeholders = ",".join("?" * len(attachment_ids))
                    async with db.execute(
                        f"SELECT * FROM message_attachments WHERE id IN ({placeholders}) ORDER BY created_at",
                        attachment_ids,
                    ) as cur:
                        new_attachments = [dict(r) for r in await cur.fetchall()]
                history.append({"role": "user", "content": await build_content(user_message, new_attachments)})

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

    if history and history[0].get("role") == "assistant":
        history[0]["_greeting"] = True

    messages = await assemble_prompt(preset_blocks, history, char_data, char_own_blocks, macros, block_images)

    for i, m in enumerate(messages):
        content = m.get("content")
        has_img = isinstance(content, list) and any(p.get("type") == "image_url" for p in content)
        has_audio = isinstance(content, list) and any(p.get("type") == "input_audio" for p in content)
        if has_img or has_audio:
            logger.debug(
                "get_prompt_context: assembled msg[%d] role=%s %s (len=%s)",
                i, m["role"], "has_image" if has_img else "has_audio",
                len(content) if isinstance(content, list) else len(str(content)),
            )

    logger.debug(
        "get_prompt_context: returning asst_msg_id=%s user_msg_id=%s next_variant_index=%d total_messages=%d",
        asst_msg_id, user_msg_id, next_variant_index, len(messages),
    )

    return PromptCtx(
        messages=messages,
        asst_msg_id=asst_msg_id,
        next_variant_index=next_variant_index,
        user_msg_id=user_msg_id,
    )



async def prepare_generation_messages(
    prov_dict: dict,
    body: StreamRequest,
    messages: list[dict],
    provider,
    chat_id: str,
) -> tuple[list[dict], dict]:
    """Apply request quirks (modality filtering, caching, field stripping,
    prefill, sampler processing, sticky routing). Thin delegator to the
    provider-aware pipeline in ``focus.providers.quirks``."""
    return await apply_request_quirks(
        prov_dict, body, messages, provider, chat_id, get_openrouter_model_modalities,
    )


def prefill_reasoning(body: StreamRequest, messages: list[dict]) -> str | None:
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
