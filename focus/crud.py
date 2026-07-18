import logging
import re
import uuid
from pathlib import Path

import aiosqlite

from focus.core.card_parser import safe_load_card
from focus.core.utils import SUFFIX_MIME_MAP, SUFFIX_MIME_MAP_IMAGES_ONLY, now_iso

logger = logging.getLogger("focus.crud")


def _strip_think_tags(text: str | None) -> str | None:
    if not text:
        return text
    stripped = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    stripped = re.sub(r"</?think>", "", stripped)
    return stripped.strip() if stripped.strip() else "New Chat"


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


async def next_position(db: aiosqlite.Connection, table: str, where_col: str, where_val: str) -> int:
    async with db.execute(
        f"SELECT COALESCE(MAX(position), -1) FROM {table} WHERE {where_col} = ?", (where_val,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] + 1


async def dynamic_update(db: aiosqlite.Connection, table: str, updates: dict, where_clause: str, where_params: list):
    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + where_params
    await db.execute(f"UPDATE {table} SET {cols} WHERE {where_clause}", vals)
    await db.commit()


async def upload_block_image(
    db: aiosqlite.Connection,
    block_id: str,
    block_source: str,
    file_data: bytes,
    filename: str,
    content_type: str | None,
    storage_dir: str,
    images_only: bool = False,
) -> dict:
    next_pos = await next_position(db, "block_images", "block_id", block_id)

    image_id = str(uuid.uuid4())
    suffix = Path(filename).suffix.lower() if filename else ".png"
    suffix = suffix or ".png"
    mime_map = SUFFIX_MIME_MAP_IMAGES_ONLY if images_only else SUFFIX_MIME_MAP
    mime = mime_map.get(suffix, "image/png" if images_only else "application/octet-stream")
    if not images_only and mime == "application/octet-stream" and content_type:
        mime = content_type

    blocks_dir = Path(storage_dir)
    blocks_dir.mkdir(parents=True, exist_ok=True)
    image_path = str(blocks_dir / f"{image_id}{suffix}")
    try:
        Path(image_path).write_bytes(file_data)
    except OSError as e:
        raise OSError(f"Failed to write uploaded file to {image_path}: {e}")

    await db.execute(
        "INSERT INTO block_images (id, block_id, block_source, image_path, mime_type, position, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (image_id, block_id, block_source, image_path, mime, next_pos, now_iso()),
    )
    await db.commit()
    return {"id": image_id, "position": next_pos, "image_path": image_path, "mime_type": mime}


async def delete_block_image(
    db: aiosqlite.Connection,
    image_id: str,
    block_id: str,
) -> None:
    async with db.execute(
        "SELECT image_path FROM block_images WHERE id = ? AND block_id = ?", (image_id, block_id)
    ) as cur:
        row = await cur.fetchone()
    if not row:
        from fastapi import HTTPException

        raise HTTPException(404, "Image not found")
    Path(row["image_path"]).unlink(missing_ok=True)
    await db.execute("DELETE FROM block_images WHERE id = ?", (image_id,))
    await db.commit()


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
        characters = []
        for r in rows:
            c = dict(r)
            c["card"] = safe_load_card(r) or {}
            c["blocks"] = await load_entity_blocks(db, "char_blocks", "character_id", r["id"])
            characters.append(c)
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
    for p in presets:
        p["blocks"] = await load_entity_blocks(db, "preset_blocks", "preset_id", p["id"])
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


async def get_personas(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute("SELECT * FROM personas ORDER BY created_at DESC") as cur:
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
        "mv.content, mv.variant_index, mv.id as variant_id, "
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

    for m in messages:
        m["attachments"] = attachments_by_variant.get(m["variant_id"], [])

    return messages


async def get_chats_sidebar(db: aiosqlite.Connection, character_id: str = None) -> list[dict]:
    query_base = """
        SELECT c.*,
               (SELECT mv.content
                FROM messages m
                JOIN message_variants mv ON m.id = mv.message_id AND m.active_index = mv.variant_index
                WHERE m.chat_id = c.id
                ORDER BY m.position DESC LIMIT 1) as last_message
        FROM chats c
    """

    chats = []
    if character_id:
        async with db.execute(
            f"{query_base} WHERE character_id = ? AND is_deleted = 0 ORDER BY updated_at DESC",
            (character_id,),
        ) as cur:
            chats = [dict(r) for r in await cur.fetchall()]
    else:
        async with db.execute(f"{query_base} WHERE is_deleted = 0 ORDER BY updated_at DESC") as cur:
            chats = [dict(r) for r in await cur.fetchall()]

    for chat in chats:
        if chat.get("last_message"):
            chat["last_message"] = _strip_think_tags(chat["last_message"])

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
