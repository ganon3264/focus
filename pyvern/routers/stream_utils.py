import json
import uuid
import tiktoken
import aiosqlite
from fastapi import HTTPException
from pyvern.prompt_chain import assemble_prompt, _build_content
from pyvern.card_parser import normalise_card

from pyvern.macros import build_base_macros

async def get_prompt_context(db: aiosqlite.Connection, chat_id: str, regenerate: bool, user_message: str, attachment_ids: list[str]) -> list[dict]:
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
        (chat_id,),
    ) as cur:
        for r in await cur.fetchall():
            msg_attachments.setdefault(r["variant_id"], []).append(dict(r))

    # ── Existing history ──────────────────────────────────────────────────────
    if regenerate:
        # Drop the last assistant message from history
        async with db.execute(
            """SELECT m.id, m.role, m.position, mv.content, mv.id as variant_id
               FROM messages m
               JOIN message_variants mv
                 ON mv.message_id = m.id AND mv.variant_index = m.active_index
               WHERE m.chat_id = ?
               ORDER BY m.position""",
            (chat_id,),
        ) as cur:
            all_rows = await cur.fetchall()

        last_asst_id = None
        for r in reversed(all_rows):
            if r["role"] == "assistant":
                last_asst_id = r["id"]
                break

        history = [
            {"role": r["role"], "content": _build_content(r["content"], msg_attachments.get(r["variant_id"], []))}
            for r in all_rows
            if r["id"] != last_asst_id
        ]
    else:
        async with db.execute(
            """SELECT m.id, m.role, mv.content, mv.id as variant_id
               FROM messages m
               JOIN message_variants mv
                 ON mv.message_id = m.id AND mv.variant_index = m.active_index
               WHERE m.chat_id = ?
               ORDER BY m.position""",
            (chat_id,),
        ) as cur:
            history_rows = await cur.fetchall()
        history = [{"role": r["role"], "content": _build_content(r["content"], msg_attachments.get(r["variant_id"], []))} for r in history_rows]

    # Append unsaved user message if provided
    if not regenerate and (user_message.strip() or attachment_ids):
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
    messages = assemble_prompt(preset_blocks, history, char_data, char_own_blocks, macros, block_images)
    
    return messages
