import json
import re
import aiosqlite

from pyvern.card_parser import normalise_card

def _strip_think_tags(text: str | None) -> str | None:
    if not text:
        return text
    # Remove everything between <think> and </think> (including the tags)
    stripped = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    # Remove any standalone <think> tags if they were malformed
    stripped = re.sub(r'</?think>', '', stripped)
    # Return stripped string if it's not empty after stripping, else return original
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

async def has_characters(db: aiosqlite.Connection) -> bool:
    async with db.execute("SELECT 1 FROM characters WHERE is_deleted = 0 LIMIT 1") as cur:
        return await cur.fetchone() is not None

async def get_characters(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute("SELECT * FROM characters WHERE is_deleted = 0 ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
        characters = []
        for r in rows:
            c = dict(r)
            try:
                c["card"] = normalise_card(json.loads(r["card_json"] or "{}"))
            except Exception:
                c["card"] = {}
            async with db.execute(
                "SELECT * FROM char_blocks WHERE character_id = ? ORDER BY position, rowid",
                (r["id"],)
            ) as bcur:
                c["blocks"] = [dict(b) for b in await bcur.fetchall()]
            await attach_images(c["blocks"], db)
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
    try:
        character["card"] = normalise_card(json.loads(row["card_json"] or "{}"))
    except Exception:
        character["card"] = {}
    return character

async def get_presets(db: aiosqlite.Connection) -> list[dict]:
    async with db.execute("SELECT * FROM presets ORDER BY created_at DESC") as cur:
        presets = [dict(r) for r in await cur.fetchall()]
    for p in presets:
        async with db.execute(
            "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid",
            (p["id"],)
        ) as cur:
            p["blocks"] = [dict(r) for r in await cur.fetchall()]
        await attach_images(p["blocks"], db)
    return presets

async def get_preset(db: aiosqlite.Connection, preset_id: str) -> dict | None:
    if not preset_id:
        return None
    async with db.execute("SELECT * FROM presets WHERE id = ?", (preset_id,)) as cur:
        row = await cur.fetchone()
    if not row:
        return None
    preset = dict(row)
    async with db.execute(
        "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid",
        (preset["id"],)
    ) as cur:
        preset["blocks"] = [dict(r) for r in await cur.fetchall()]
    await attach_images(preset["blocks"], db)
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

async def get_chat_messages(db: aiosqlite.Connection, chat_id: str) -> list[dict]:
    async with db.execute("""
        SELECT m.id, m.role, m.position, m.active_index, mv.content, mv.variant_index, mv.id as variant_id,
               (SELECT COUNT(*) FROM message_variants WHERE message_id = m.id) as variant_count
        FROM messages m
        JOIN message_variants mv ON mv.message_id = m.id AND mv.variant_index = m.active_index
        WHERE m.chat_id = ?
        ORDER BY m.position
    """, (chat_id,)) as cur:
        messages = [dict(r) for r in await cur.fetchall()]

    async with db.execute(
        "SELECT id, variant_id, file_path, mime_type FROM message_attachments WHERE chat_id = ? AND variant_id IS NOT NULL",
        (chat_id,)
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
            (character_id,)
        ) as cur:
            chats = [dict(r) for r in await cur.fetchall()]
    else:
        async with db.execute(f"{query_base} WHERE is_deleted = 0 ORDER BY updated_at DESC") as cur:
            chats = [dict(r) for r in await cur.fetchall()]
            
    for chat in chats:
        if chat.get("last_message"):
            chat["last_message"] = _strip_think_tags(chat["last_message"])
            
    return chats
