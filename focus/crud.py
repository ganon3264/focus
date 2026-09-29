import json
import logging

import aiosqlite

from focus.core.card_parser import safe_load_card
from focus.core.media import tool_image_url

logger = logging.getLogger("focus.crud")

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
    await _attach_blocks(db, characters, "char_blocks", "character_id", "blocks")
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
    await _attach_blocks(db, presets, "preset_blocks", "preset_id", "blocks")
    return presets


async def _attach_blocks(db: aiosqlite.Connection, rows: list[dict], table: str, fk_col: str, key: str) -> None:
    """Batch-load child blocks for entity rows and attach them under *key*."""
    if not rows:
        return
    ids = [r["id"] for r in rows]
    placeholders = ",".join("?" * len(ids))
    async with db.execute(
        f"SELECT * FROM {table} WHERE {fk_col} IN ({placeholders}) ORDER BY position, rowid", ids
    ) as cur:
        block_rows = await cur.fetchall()
    by_parent: dict[str, list[dict]] = {}
    for br in block_rows:
        by_parent.setdefault(br[fk_col], []).append(dict(br))
    for r in rows:
        r[key] = by_parent.get(r["id"], [])


async def get_preset_blocks(db: aiosqlite.Connection, preset_id: str | None) -> list[dict]:
    if not preset_id:
        return []
    return await load_entity_blocks(db, "preset_blocks", "preset_id", preset_id)


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
        "m.id, m.chat_id, m.role, m.position, m.active_index, "
        "mv.content, mv.variant_meta, mv.segments_json, mv.variant_index, mv.id as variant_id, "
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
        try:
            vm = json.loads(m["variant_meta"]) if m.get("variant_meta") else {}
        except (TypeError, ValueError):
            vm = {}
        m["reasoning"] = vm.get("reasoning")
        m["segments"] = render_message_segments(m["content"], m["variant_meta"], m.get("segments_json"))
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
                    "image_data": (
                        tool_image_url(tc['result_image_path']) if tc.get("result_image_path")
                        else None
                    ),
                }
                for tc in tcs
            ]

    return messages


async def get_lineage_messages(db: aiosqlite.Connection, chat_id: str) -> list[dict]:
    """All messages visible in *chat_id*'s lineage, oldest first.

    Ancestors contribute only the messages up to the fork point recorded on the
    summary their descendant was created from. Each message carries its own
    ``chat_id`` and an ``is_ancestor`` flag so the template can render inherited
    turns read-only.
    """
    # Walk from the target up to the root, recording the cut position per chat.
    path: list[tuple[str, int | None]] = []
    current: str | None = chat_id
    cut: int | None = None
    while current:
        path.append((current, cut))
        async with db.execute(
            "SELECT parent_chat_id, summary_id FROM chats WHERE id = ?", (current,)
        ) as cur:
            row = await cur.fetchone()
        if not row or not row["parent_chat_id"]:
            break
        cut = None
        if row["summary_id"]:
            async with db.execute(
                "SELECT covered_to_position FROM chat_summaries WHERE id = ?",
                (row["summary_id"],),
            ) as cur:
                summary = await cur.fetchone()
            if summary and summary["covered_to_position"] >= 0:
                cut = summary["covered_to_position"]
        current = row["parent_chat_id"]
    path.reverse()

    messages: list[dict] = []
    last_ancestor_idx: int | None = None
    for cid, cut in path:
        rows = await get_chat_messages(db, cid)
        if cut is not None:
            rows = [m for m in rows if m["position"] <= cut]
        for m in rows:
            m["is_ancestor"] = cid != chat_id
            if m["is_ancestor"]:
                last_ancestor_idx = len(messages)
            messages.append(m)
    if last_ancestor_idx is not None:
        messages[last_ancestor_idx]["is_summary_last"] = True
    return messages


CHAT_PAGE_SIZE = 15
CHAT_PAGE_SIZE_MAX = 50


def _page_window(page: int, total_pages: int, width: int = 5) -> list[int]:
    """The contiguous run of page numbers to show, centred on *page*."""
    if total_pages <= width:
        return list(range(1, total_pages + 1))
    start = max(1, min(page - width // 2, total_pages - width + 1))
    return list(range(start, start + width))


async def get_chats_sidebar(
    db: aiosqlite.Connection,
    character_id: str = None,
    page: int = 1,
    page_size: int = CHAT_PAGE_SIZE,
) -> dict:
    """One page of sidebar chats plus pagination metadata (page is clamped)."""
    page_size = max(1, min(page_size, CHAT_PAGE_SIZE_MAX))
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

    where = "WHERE c.is_deleted = 0"
    params: list = []
    if character_id:
        where += " AND c.character_id = ?"
        params.append(character_id)

    async with db.execute(f"SELECT COUNT(*) FROM chats c {where}", params) as cur:
        total = (await cur.fetchone())[0]

    total_pages = max(1, -(-total // page_size))
    page = min(max(1, page), total_pages)
    offset = (page - 1) * page_size

    async with db.execute(
        f"{query_base} {where} ORDER BY c.updated_at DESC, c.id DESC LIMIT ? OFFSET ?",
        (*params, page_size, offset),
    ) as cur:
        chats = [dict(r) for r in await cur.fetchall()]

    for chat in chats:
        if chat.get("last_message"):
            chat["last_message"] = chat["last_message"].strip() or "New Chat"

    return {
        "chats": chats,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "page_numbers": _page_window(page, total_pages),
    }


async def get_chat_page(
    db: aiosqlite.Connection, chat_id: str, character_id: str = None, page_size: int = CHAT_PAGE_SIZE
) -> int:
    """1-based page that contains *chat_id* under the sidebar ordering."""
    where = "WHERE is_deleted = 0"
    params: list = []
    if character_id:
        where += " AND character_id = ?"
        params.append(character_id)

    async with db.execute(
        f"""SELECT rn FROM (
                SELECT id, ROW_NUMBER() OVER (ORDER BY updated_at DESC, id DESC) AS rn
                FROM chats {where}
            ) WHERE id = ?""",
        (*params, chat_id),
    ) as cur:
        row = await cur.fetchone()

    if not row:
        return 1
    return (row["rn"] - 1) // page_size + 1


async def get_counts(db: aiosqlite.Connection, character_id: str | None, persona_id: str | None) -> dict:
    """Counts mirror assemble_prompt's block_id-keyed image lookups (source is ignored there too).

    char_attachments: direct character images → injected with description/personality.
    char_block_attachments: images on the character's own blocks → injected at those blocks.
    persona_attachments: direct persona images → injected with the persona text.
    """
    counts = {
        "char_blocks": 0,
        "char_attachments": 0,
        "char_block_attachments": 0,
        "persona_attachments": 0,
    }

    if character_id:
        async with db.execute("SELECT COUNT(*) FROM char_blocks WHERE character_id = ?", (character_id,)) as cur:
            counts["char_blocks"] = (await cur.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM block_images WHERE block_id = ?", (character_id,)) as cur:
            counts["char_attachments"] = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT COUNT(*) FROM block_images WHERE block_id IN (SELECT id FROM char_blocks WHERE character_id = ?)",
            (character_id,),
        ) as cur:
            counts["char_block_attachments"] = (await cur.fetchone())[0]

    if persona_id:
        async with db.execute("SELECT COUNT(*) FROM block_images WHERE block_id = ?", (persona_id,)) as cur:
            counts["persona_attachments"] = (await cur.fetchone())[0]

    return counts



async def get_active_provider(db: aiosqlite.Connection) -> dict:
    async with db.execute("SELECT value FROM settings WHERE key = 'active_provider_id'") as cur:
        row = await cur.fetchone()
    provider_id = row["value"] if row else None

    async with db.execute("SELECT value FROM settings WHERE key = 'active_provider_type'") as cur:
        row = await cur.fetchone()
    provider_type = row["value"] if row else None

    return {"provider_id": provider_id, "provider_type": provider_type}






