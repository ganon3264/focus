import asyncio
import logging
import uuid
import aiosqlite
from fastapi import HTTPException
from focus.prompt_chain import assemble_prompt, _build_content
from focus.card_parser import safe_load_card
from focus.macros import build_base_macros
from focus.utils import now_iso
import focus.crud as crud

logger = logging.getLogger("focus.routers.stream_utils")

_chat_locks: dict[str, asyncio.Lock] = {}

async def _get_history(db: aiosqlite.Connection, chat_id: str, regenerate: bool):
    """Load message history and message attachments for a chat."""
    msg_attachments: dict[str, list[dict]] = {}
    async with db.execute(
        "SELECT * FROM message_attachments WHERE chat_id = ? AND variant_id IS NOT NULL ORDER BY created_at",
        (chat_id,),
    ) as cur:
        for r in await cur.fetchall():
            msg_attachments.setdefault(r["variant_id"], []).append(dict(r))

    if regenerate:
        all_rows = await crud.fetch_active_variants(db, chat_id)

        last_asst_id = None
        last_asst_variant_count = 0
        for r in reversed(all_rows):
            if r["role"] == "assistant":
                last_asst_id = r["id"]
                last_asst_variant_count = r["variant_count"]
                break

        history = [
            {"role": r["role"], "content": _build_content(r["content"], msg_attachments.get(r["variant_id"], []))}
            for r in all_rows
            if r["id"] != last_asst_id
        ]
        return history, last_asst_id, last_asst_variant_count
    else:
        history_rows = await crud.fetch_active_variants(db, chat_id)
        history = [{"role": r["role"], "content": _build_content(r["content"], msg_attachments.get(r["variant_id"], []))} for r in history_rows]
        return history, None, 0


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
    # ── Validate chat ────────────────────────────────────────────────────────
    async with db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)) as cur:
        chat = await cur.fetchone()
    if not chat:
        raise HTTPException(404, "Chat not found")
    chat = dict(chat)

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
            card_json = safe_load_card(char_row) or {}
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

    # ── History ───────────────────────────────────────────────────────────────
    history, asst_msg_id, next_variant_index = await _get_history(db, chat_id, regenerate)

    # ── User message persistence / history append ─────────────────────────────
    user_msg_id = None
    if not regenerate:
        if persist:
            lock = _chat_locks.setdefault(chat_id, asyncio.Lock())
            async with lock:
                now = now_iso()
                async with db.execute(
                    "SELECT MAX(position) FROM messages WHERE chat_id = ?", (chat_id,)
                ) as cur:
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

                    # Bind any attached files to the newly created user message
                    if attachment_ids:
                        placeholders = ",".join("?" * len(attachment_ids))
                        await db.execute(
                            f"UPDATE message_attachments SET message_id = ?, variant_id = ? WHERE id IN ({placeholders})",
                            [user_msg_id, user_variant_id] + attachment_ids
                        )

                        async with db.execute(
                            f"SELECT * FROM message_attachments WHERE id IN ({placeholders}) ORDER BY created_at",
                            attachment_ids
                        ) as cur:
                            new_attachments = [dict(r) for r in await cur.fetchall()]
                    else:
                        new_attachments = []

                    history.append({"role": "user", "content": _build_content(user_message, new_attachments)})
                    next_pos += 1

                # Create assistant message slot
                asst_msg_id = str(uuid.uuid4())
                await db.execute(
                    "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (asst_msg_id, chat_id, "assistant", next_pos, 0, now),
                )
                next_variant_index = 0
                await db.commit()
        else:
            # Read-only path (itemizer): just append to history in memory
            if user_message.strip() or attachment_ids:
                new_attachments = []
                if attachment_ids:
                    placeholders = ",".join("?" * len(attachment_ids))
                    async with db.execute(
                        f"SELECT * FROM message_attachments WHERE id IN ({placeholders}) ORDER BY created_at",
                        attachment_ids
                    ) as cur:
                        new_attachments = [dict(r) for r in await cur.fetchall()]
                history.append({"role": "user", "content": _build_content(user_message, new_attachments)})

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
    if history and history[0].get("role") == "assistant":
        history[0]["_greeting"] = True

    messages = assemble_prompt(preset_blocks, history, char_data, char_own_blocks, macros, block_images)

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


def apply_claude_caching(messages: list[dict], cache_enabled: bool, cache_ttl: str = "ephemeral", cache_depth: int = 5) -> list[dict]:
    """Inject cache_control breakpoints for Claude prompt caching on OpenRouter.

    Static breakpoint covers all preset blocks + the character greeting (if present).
    Sliding breakpoint covers *all but* the most recent `cache_depth` user-assistant
    exchanges, placed on the user message that far back.

    Enforces Anthropic's 4-breakpoint limit by stripping any existing cache_control
    markers before adding the two new ones.
    """
    if not cache_enabled or not messages:
        return messages

    cc: dict = {"type": "1h"} if cache_ttl == "1h" else {"type": "ephemeral"}

    # ── Strip any existing cache_control to enforce the 4-breakpoint limit ──
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                part.pop("cache_control", None)

    def _inject_cache(msg: dict) -> bool:
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = [{"type": "text", "text": content, "cache_control": cc}]
            return True
        if isinstance(content, list):
            for part in reversed(content):
                if part.get("type") == "text":
                    part["cache_control"] = cc
                    return True
            content.append({"type": "text", "text": "", "cache_control": cc})
            return True
        return False

    # ── Static breakpoint ──────────────────────────────────────────────────
    static_idx = 0

    # Preferred: explicit greeting tag placed by get_prompt_context()
    for i, msg in enumerate(messages):
        if msg.get("_greeting"):
            static_idx = i
            break
    else:
        # Fallback: last message before the first user message
        for i, msg in enumerate(messages):
            if msg.get("role") == "user":
                static_idx = max(0, i - 1)
                break

    _inject_cache(messages[static_idx])

    # ── Sliding breakpoint ─────────────────────────────────────────────────
    # Count user-role messages from the end; place breakpoint cache_depth
    # exchanges before the current query (cache_depth+1th user from end).
    user_count = 0
    bp_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "user":
            user_count += 1
            if user_count == cache_depth + 1:
                bp_idx = i
                break
    if bp_idx > static_idx:
        _inject_cache(messages[bp_idx])

    # ── Clean up metadata tags ─────────────────────────────────────────────
    for msg in messages:
        msg.pop("_greeting", None)

    return messages
