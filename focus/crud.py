import json
import logging

import aiosqlite

from focus.core.card_parser import safe_load_card

logger = logging.getLogger("focus.crud")


def extract_image_from_extra(extra_json: str | None) -> str | None:
    if not extra_json:
        return None
    try:
        extra = json.loads(extra_json)
        content = extra.get("content", [])
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return part.get("image_url", {}).get("url")
    except (json.JSONDecodeError, TypeError):
        pass
    return None


async def attach_images(blocks: list[dict], db: aiosqlite.Connection) -> list[dict]:
    if not blocks:
        return blocks
    ids = [b["id"] for b in blocks]
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT id, block_id, image_path, mime_type, position FROM block_images WHERE block_id IN ({placeholders}) ORDER BY position",
        ids,
    ) as cur:
        rows = await cur.fetchall()
    images_by_block: dict[str, list] = {}
    for r in rows:
        images_by_block.setdefault(r["block_id"], []).append(dict(r))
    for b in blocks:
        b["images"] = images_by_block.get(b["id"], [])
    return blocks


async def verify_entity_exists(
    db: aiosqlite.Connection,
    table: str,
    entity_id: str,
    parent_col: str | None = None,
    parent_id: str | None = None,
) -> None:
    if parent_col and parent_id is not None:
        async with db.execute(
            f"SELECT id FROM {table} WHERE id = ? AND {parent_col} = ?", (entity_id, parent_id)
        ) as cur:
            row = await cur.fetchone()
    else:
        async with db.execute(f"SELECT id FROM {table} WHERE id = ?", (entity_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException

        raise HTTPException(404, f"{table.split('_')[0].capitalize()} not found")


async def has_characters(db: aiosqlite.Connection) -> bool:
    async with db.execute("SELECT 1 FROM characters WHERE is_deleted = 0 LIMIT 1") as cur:
        return await cur.fetchone() is not None


async def load_entity_blocks(
    db: aiosqlite.Connection,
    table: str,
    parent_col: str,
    parent_id: str,
) -> list[dict]:
    async with db.execute(
        f"SELECT * FROM {table} WHERE {parent_col} = ? ORDER BY position, rowid", (parent_id,)
    ) as cur:
        blocks = [dict(r) for r in await cur.fetchall()]
    await attach_images(blocks, db)
    return blocks


async def get_characters(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute("SELECT * FROM characters WHERE is_deleted = 0 ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
        characters = [dict(r) for r in rows]
    for c in characters:
        c["card"] = safe_load_card(c) or {}
    # Batch-load blocks for all characters
    if characters:
        ids = [c["id"] for c in characters]
        placeholders = ",".join("?" * len(ids))
        async with db.execute(
            f"SELECT * FROM char_blocks WHERE character_id IN ({placeholders}) ORDER BY position, rowid", ids
        ) as cur:
            block_rows = await cur.fetchall()
        blocks_by_char: dict[str, list[dict]] = {}
        for br in block_rows:
            blocks_by_char.setdefault(br["character_id"], []).append(dict(br))
        for c in characters:
            c["blocks"] = blocks_by_char.get(c["id"], [])
    await attach_images(characters, db)
    return characters


async def get_character(db: aiosqlite.Connection, character_id: str) -> dict | None:
    if not character_id:
        return None
    async with db.execute("SELECT * FROM characters WHERE id = ?", (character_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    character = dict(row)
    character["card"] = safe_load_card(row) or {}
    return character


async def get_presets(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute("SELECT * FROM presets ORDER BY created_at DESC") as cur:
        presets = [dict(r) for r in await cur.fetchall()]
    # Batch-load blocks for all presets
    if presets:
        ids = [p["id"] for p in presets]
        placeholders = ",".join("?" * len(ids))
        async with db.execute(
            f"SELECT * FROM preset_blocks WHERE preset_id IN ({placeholders}) ORDER BY position, rowid", ids
        ) as cur:
            block_rows = await cur.fetchall()
        blocks_by_preset: dict[str, list[dict]] = {}
        for br in block_rows:
            blocks_by_preset.setdefault(br["preset_id"], []).append(dict(br))
        for p in presets:
            p["blocks"] = blocks_by_preset.get(p["id"], [])
    return presets


async def get_preset(db: aiosqlite.Connection, preset_id: str) -> dict | None:
    if not preset_id:
        return None
    async with db.execute("SELECT * FROM presets WHERE id = ?", (preset_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    preset = dict(row)
    preset["blocks"] = await load_entity_blocks(db, "preset_blocks", "preset_id", preset_id)
    return preset


async def get_providers(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute("SELECT * FROM providers ORDER BY created_at DESC") as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_personas(db: aiosqlite.Connection, include_deleted: bool = False) -> list[dict]:
    where = "" if include_deleted else "WHERE is_deleted = 0"
    async with db.execute(f"SELECT * FROM personas {where} ORDER BY created_at DESC") as cur:
        personas = [dict(r) for r in await cur.fetchall()]
    await attach_images(personas, db)
    return personas


async def get_persona(db: aiosqlite.Connection, persona_id: str = None) -> dict | None:
    if persona_id:
        async with db.execute("SELECT * FROM personas WHERE id = ?", (persona_id,)) as cur:
            row = await cur.fetchone()
    else:
        async with db.execute("SELECT * FROM personas ORDER BY created_at LIMIT 1") as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def fetch_active_variants(db: aiosqlite.Connection, chat_id: str, extra_cols: str = "") -> list[dict]:
    """Fetch messages with their active variant content for a chat.

    Returns rows with: id, role, position, active_index, content,
    variant_index, variant_id, variant_count plus any extra_cols.
    """
    cols = (
        "m.id, m.role, m.position, m.active_index, "
        "mv.content, mv.reasoning, mv.segments_json, mv.variant_index, mv.id as variant_id, "
        "mv.created_at, mv.model_name, "
        "(SELECT COUNT(*) FROM message_variants WHERE message_id = m.id) as variant_count"
    )
    if extra_cols:
        cols += ", " + extra_cols
    async with db.execute(
        f"""SELECT {cols}
            FROM messages m
            JOIN message_variants mv ON mv.message_id = m.id AND mv.variant_index = m.active_index
            WHERE m.chat_id = ?
            ORDER BY m.position""",
        (chat_id,),
    ) as cur:
        return [dict(r) for r in await cur.fetchall()]


async def get_chat_messages(db: aiosqlite.Connection, chat_id: str) -> list[dict]:
    messages = await fetch_active_variants(db, chat_id)

    async with db.execute(
        "SELECT id, variant_id, file_path, mime_type FROM message_attachments WHERE chat_id = ? AND variant_id IS NOT NULL",
        (chat_id,),
    ) as cur:
        attachments = await cur.fetchall()

    attachments_by_variant = {}
    for a in attachments:
        attachments_by_variant.setdefault(a["variant_id"], []).append(dict(a))

    # Load tool_calls for each message, keyed by variant_id
    async with db.execute(
        "SELECT * FROM tool_calls WHERE chat_id = ? AND variant_id IS NOT NULL ORDER BY created_at",
        (chat_id,),
    ) as cur:
        tool_calls_rows = await cur.fetchall()

    tool_calls_by_variant: dict[str, list[dict]] = {}
    for tc in tool_calls_rows:
        tool_calls_by_variant.setdefault(tc["variant_id"], []).append(dict(tc))

    from focus.core.message_render import render_message_segments

    for m in messages:
        m["attachments"] = attachments_by_variant.get(m["variant_id"], [])
        m["segments"] = render_message_segments(m["content"], m.get("reasoning"), m.get("segments_json"))
        tcs = tool_calls_by_variant.get(m["variant_id"], [])
        if tcs:
            m["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["tool_name"],
                        "arguments": tc["arguments"],
                    },
                    "result": tc["result"],
                    "is_error": bool(tc["is_error"]),
                    "image_data": extract_image_from_extra(tc.get("extra_message_json")),
                }
                for tc in tcs
            ]

    return messages


async def get_chats_sidebar(db: aiosqlite.Connection, character_id: str = None) -> list[dict]:
    query_base = """
        SELECT c.*,
               p.name as persona_name,
               p.avatar_path as persona_avatar,
               (SELECT mv.content
                FROM messages m
                JOIN message_variants mv ON m.id = mv.message_id AND m.active_index = mv.variant_index
                WHERE m.chat_id = c.id
                ORDER BY m.position DESC LIMIT 1) as last_message
        FROM chats c
        LEFT JOIN personas p ON p.id = c.persona_id
    """

    chats = []
    if character_id:
        async with db.execute(
            f"{query_base} WHERE c.character_id = ? AND c.is_deleted = 0 ORDER BY c.updated_at DESC",
            (character_id,),
        ) as cur:
            chats = [dict(r) for r in await cur.fetchall()]
    else:
        async with db.execute(f"{query_base} WHERE c.is_deleted = 0 ORDER BY c.updated_at DESC") as cur:
            chats = [dict(r) for r in await cur.fetchall()]

    for chat in chats:
        if chat.get("last_message"):
            chat["last_message"] = chat["last_message"].strip() or "New Chat"

    return chats


async def get_counts(db: aiosqlite.Connection, character_id: str | None, persona_id: str | None) -> dict:
    counts = {"char_blocks": 0, "char_attachments": 0, "persona_attachments": 0}

    if character_id:
        async with db.execute("SELECT id FROM char_blocks WHERE character_id = ?", (character_id,)) as cur:
            char_blocks_rows = await cur.fetchall()
            counts["char_blocks"] = len(char_blocks_rows)

            async with db.execute(
                "SELECT COUNT(*) FROM block_images WHERE block_id = ? AND block_source = 'char'",
                (character_id,),
            ) as img_cur:
                row = await img_cur.fetchone()
                counts["char_attachments"] += row[0] if row else 0

            if char_blocks_rows:
                block_ids = [r["id"] for r in char_blocks_rows]
                placeholders = ",".join("?" * len(block_ids))
                async with db.execute(
                    f"SELECT COUNT(*) FROM block_images WHERE block_id IN ({placeholders}) AND block_source = 'char'",
                    block_ids,
                ) as img_cur:
                    row = await img_cur.fetchone()
                    counts["char_attachments"] += row[0] if row else 0

    if persona_id:
        async with db.execute(
            "SELECT COUNT(*) FROM block_images WHERE block_id = ? AND block_source = 'char'",
            (persona_id,),
        ) as img_cur:
            row = await img_cur.fetchone()
            counts["persona_attachments"] += row[0] if row else 0

    return counts



async def get_active_provider(db: aiosqlite.Connection) -> dict:
    async with db.execute("SELECT value FROM settings WHERE key = 'active_provider_id'") as cur:
        row = await cur.fetchone()
    provider_id = row["value"] if row else None

    async with db.execute("SELECT value FROM settings WHERE key = 'active_provider_type'") as cur:
        row = await cur.fetchone()
    provider_type = row["value"] if row else None

    return {"provider_id": provider_id, "provider_type": provider_type}






