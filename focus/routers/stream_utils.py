import asyncio
import html
import json
import logging
import uuid

import aiosqlite
from fastapi import HTTPException

import focus.crud as crud
from focus.core.card_parser import safe_load_card
from focus.core.macros import build_base_macros
from focus.core.models import StreamRequest
from focus.core.utils import now_iso
from focus.prompt_chain import assemble_prompt, build_content
from focus.routers.providers import get_openrouter_model_modalities

logger = logging.getLogger("focus.routers.stream_utils")

_chat_locks: dict[str, asyncio.Lock] = {}
_chat_locks_creation_lock = asyncio.Lock()


async def _make_assistant_slot(db: aiosqlite.Connection, chat_id: str) -> str:
    """Insert a new assistant message row and return its id."""
    now = now_iso()
    async with db.execute("SELECT MAX(position) FROM messages WHERE chat_id = ?", (chat_id,)) as cur:
        pos_row = await cur.fetchone()
    next_pos = (pos_row[0] if pos_row[0] is not None else -1) + 1
    asst_id = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (asst_id, chat_id, "assistant", next_pos, 0, now),
    )
    await db.commit()
    return asst_id


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
            _append_segmented_tool_history(history, segments, tcs)
            return

    content = await build_content(content_text, msg_attachments.get(row["variant_id"], []))

    entry: dict = {
        "role": row["role"],
        "content": content,
    }
    if row["role"] == "assistant" and row.get("reasoning"):
        entry["reasoning"] = row["reasoning"]

    if tcs and row["role"] == "assistant":
        entry["tool_calls"] = [_tool_calls_payload(tc) for tc in tcs]

    history.append(entry)

    # Insert synthetic tool-role messages after the assistant message,
    # interleaved with any extra_message user messages (e.g. images)
    for tc in tcs:
        _append_tool_messages(history, tc)


def _tool_calls_payload(tc: dict) -> dict:
    return {
        "id": tc["id"],
        "type": "function",
        "function": {
            "name": tc["tool_name"],
            "arguments": tc["arguments"],
        },
    }


def _append_tool_messages(history: list, tc: dict) -> None:
    """Append a synthetic tool-role message for *tc*, followed by its
    extra_message user message (e.g. a tool-returned image) if present."""
    history.append({
        "role": "tool",
        "tool_call_id": tc["id"],
        "content": tc["result"] or "",
    })
    if tc.get("extra_message_json"):
        history.append(json.loads(tc["extra_message_json"]))


def _append_segmented_tool_history(history: list, segments: list, tcs: list) -> None:
    """Rebuild per-iteration history from stored segments.

    Each ``tool_boundary`` segment with ``tool_calls`` closes an assistant
    chunk; the final chunk (the post-tool reaction) becomes a plain assistant
    entry. Reasoning segments store escaped HTML — unescaped here, which is
    the exact inverse of ``_escape_html`` in message_render.py.

    Segment calls carry the *provider* call id while ``tool_calls`` rows use
    a local uuid as PK, so calls are matched to rows by consumption order
    (boundaries are in generation order; rows are loaded ``ORDER BY
    created_at``), validated by tool name.
    """
    ordered = list(tcs)  # already ORDER BY created_at from _get_history
    pos = 0
    text_parts: list[str] = []
    reasoning_parts: list[str] = []

    def flush(group: list | None) -> None:
        text = "".join(text_parts).strip()
        reasoning = "".join(reasoning_parts).strip()
        if not text and not reasoning and not group:
            return
        entry: dict = {"role": "assistant", "content": text}
        if reasoning:
            entry["reasoning"] = reasoning
        if group:
            entry["tool_calls"] = [_tool_calls_payload(tc) for tc in group]
        history.append(entry)
        for tc in group or []:
            _append_tool_messages(history, tc)
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
            flush(group)
    flush(None)


async def get_prompt_context(
    db: aiosqlite.Connection,
    chat_id: str,
    regenerate: bool,
    user_message: str,
    attachment_ids: list[str],
    persist: bool = False,
) -> dict:
    """Load chat state and assemble the full prompt context for generation.

    Validates the chat, loads character/persona/preset data, builds macros,
    fetches message history, persists the user message (when persist=True),
    loads block images for all relevant blocks, and assembles the final
    message list via assemble_prompt().

    Returns dict with keys: messages, asst_msg_id, next_variant_index, user_msg_id.
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

    macros = build_base_macros(char_data)

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

    user_msg_id = None
    if not regenerate:
        if persist:
            async with _chat_locks_creation_lock:
                if chat_id not in _chat_locks:
                    _chat_locks[chat_id] = asyncio.Lock()
            lock = _chat_locks[chat_id]
            async with lock:
                now = now_iso()
                async with db.execute("SELECT MAX(position) FROM messages WHERE chat_id = ?", (chat_id,)) as cur:
                    pos_row = await cur.fetchone()
                next_pos = (pos_row[0] if pos_row[0] is not None else -1) + 1

                # Only create a user message if there's actual text or attachments
                if user_message.strip() or attachment_ids:
                    user_msg_id = str(uuid.uuid4())
                    user_variant_id = str(uuid.uuid4())
                    await db.execute(
                        "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                        (user_msg_id, chat_id, "user", next_pos, 0, now),
                    )
                    await db.execute(
                        "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                        (user_variant_id, user_msg_id, 0, user_message, now),
                    )

                    logger.debug(
                        "get_prompt_context: created user msg id=%s variant_id=%s next_pos=%d",
                        user_msg_id, user_variant_id, next_pos,
                    )

                    # Bind any attached files to the newly created user message
                    if attachment_ids:
                        placeholders = ",".join("?" * len(attachment_ids))
                        await db.execute(
                            f"UPDATE message_attachments SET message_id = ?, variant_id = ? WHERE id IN ({placeholders})",
                            [user_msg_id, user_variant_id] + attachment_ids,
                        )

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

    return {
        "messages": messages,
        "asst_msg_id": asst_msg_id,
        "next_variant_index": next_variant_index,
        "user_msg_id": user_msg_id,
    }


def filter_unsupported_modalities(messages: list[dict], supported_modalities: list[str] | None) -> list[dict]:
    """Strip media blocks (image_url, input_audio) for models that don't support them.

    If a model only accepts text, all image/audio/file parts are removed and
    single-text content arrays are collapsed back to plain strings.
    """
    if not supported_modalities:
        return messages

    can_image = "image" in supported_modalities
    can_audio = "audio" in supported_modalities
    can_file = "file" in supported_modalities

    if can_image and can_audio:
        return messages

    filtered: list[dict] = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            filtered.append(msg)
            continue

        new_parts = []
        for part in content:
            pt = part.get("type")
            if pt == "text":
                new_parts.append(part)
            elif pt == "image_url" and can_image:
                new_parts.append(part)
            elif pt == "input_audio" and can_audio:
                new_parts.append(part)
            elif pt == "file" and can_file:
                new_parts.append(part)

        if not new_parts:
            continue
        if len(new_parts) == 1 and new_parts[0].get("type") == "text":
            filtered.append({"role": msg["role"], "content": new_parts[0].get("text", "")})
        else:
            filtered.append({"role": msg["role"], "content": new_parts})

    return filtered


def apply_claude_caching(
    messages: list[dict],
    cache_enabled: bool,
    cache_ttl: str = "5m",
    cache_depth: int = 5,
) -> list[dict]:
    if not cache_enabled or not messages:
        return messages

    # cache_control is always {"type": "ephemeral"}; duration is the
    # separate "ttl" field ("5m" default/omitted, or "1h").
    cc: dict = {"type": "ephemeral", "ttl": "1h"} if cache_ttl == "1h" else {"type": "ephemeral"}

    # Strip existing cache control so we never exceed the 4-breakpoint limit
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    part.pop("cache_control", None)

    def _inject_cache(msg: dict) -> bool:
        content = msg.get("content")
        if isinstance(content, str):
            if not content:
                return False
            msg["content"] = [{"type": "text", "text": content, "cache_control": cc}]
            return True
        if isinstance(content, list) and content:
            # cache_control is valid on any block type (text, image,
            # tool_use, tool_result, document) - just tag the last one.
            for part in reversed(content):
                if isinstance(part, dict) and part.get("type"):
                    part["cache_control"] = cc
                    return True
        return False

    # 1. Always cache the system/character instructions at the very beginning
    _inject_cache(messages[0])

    # 2. Sliding breakpoint further back in the conversation
    user_indices = [i for i, msg in enumerate(messages) if msg.get("role") == "user"]

    bp_idx = None
    if len(user_indices) >= cache_depth + 1:
        bp_idx = user_indices[-(cache_depth + 1)]
    elif len(user_indices) > 1:
        bp_idx = user_indices[-2]

    # Skip if it's the same message as the system breakpoint (avoid wasted work)
    if bp_idx is not None and bp_idx != 0:
        _inject_cache(messages[bp_idx])

    for msg in messages:
        msg.pop("_greeting", None)

    return messages


async def prepare_generation_messages(
    prov_dict: dict,
    body: StreamRequest,
    messages: list[dict],
    provider,
    chat_id: str,
) -> tuple[list[dict], dict]:
    """Apply modality filtering, caching, field stripping, prefill,
    sampler processing, and OpenRouter sticky routing.
    Returns (filtered_messages, gen_kwargs)."""

    s = dict(body.samplers or {})
    if s.pop("disable_multimodal", False):
        messages = filter_unsupported_modalities(messages, ["text"])

    if prov_dict.get("type") == "openrouter":
        modalities = await get_openrouter_model_modalities(prov_dict.get("model", ""))
        if modalities:
            messages = filter_unsupported_modalities(messages, modalities)

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
