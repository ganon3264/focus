from __future__ import annotations

import json
import uuid
from pathlib import Path

import aiosqlite

from focus.core.utils import now_iso, variable_group_name


async def create_preset(db: aiosqlite.Connection, name: str) -> str:
    preset_id = str(uuid.uuid4())
    now = now_iso()
    await db.execute(
        "INSERT INTO presets (id, name, created_at) VALUES (?, ?, ?)",
        (preset_id, name, now),
    )
    defaults = [
        (str(uuid.uuid4()), preset_id, "System Prompt",
         "A default system prompt (please replace it!)", "system", 1, 0.0, "text"),
        (str(uuid.uuid4()), preset_id, "Char Description", "", "user", 1, 1.0, "char_description"),
        (str(uuid.uuid4()), preset_id, "User Persona", "", "user", 1, 2.0, "user_persona"),
        (str(uuid.uuid4()), preset_id, "Char Blocks", "", "system", 1, 3.0, "char_blocks"),
        (str(uuid.uuid4()), preset_id, "Chat History", "", "system", 1, 4.0, "chat_history"),
    ]
    await db.executemany(
        "INSERT INTO preset_blocks (id, preset_id, name, content, role, enabled, position, block_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        defaults,
    )
    return preset_id


async def update_preset(db: aiosqlite.Connection, preset_id: str, name: str) -> None:
    await db.execute("UPDATE presets SET name = ? WHERE id = ?", (name, preset_id))


async def delete_preset(db: aiosqlite.Connection, preset_id: str) -> None:
    await db.execute("DELETE FROM presets WHERE id = ?", (preset_id,))


async def import_preset(db: aiosqlite.Connection, file_content: bytes, filename: str = "") -> dict:
    data = json.loads(file_content)
    preset_name = Path(filename).stem
    preset_id = str(uuid.uuid4())
    now = now_iso()
    await db.execute(
        "INSERT INTO presets (id, name, created_at) VALUES (?, ?, ?)",
        (preset_id, preset_name, now),
    )

    sentinel_map = {
        "chatHistory": "chat_history",
        "charDescription": "char_description",
        "charPersonality": "char_personality",
        "personaDescription": "user_persona",
    }

    prompts = data.get("prompts", [])
    prompt_order = data.get("prompt_order", [])

    enabled_map: dict[str, bool] = {}
    order_list: list[str] = []
    if prompt_order:
        best_profile = max(prompt_order, key=lambda p: len(p.get("order", [])))
        for entry in best_profile.get("order", []):
            ident = entry["identifier"]
            enabled_map[ident] = entry.get("enabled", True)
            order_list.append(ident)

    block_map: dict[str, dict] = {}
    blocks_in_order: list[dict] = []

    for prompt in prompts:
        identifier = prompt.get("identifier", "")
        block_type = sentinel_map.get(identifier, "text")
        enabled = enabled_map.get(identifier)
        if enabled is None:
            enabled = prompt.get("enabled", True)
        is_in_chat = prompt.get("injection_position") == 1
        block = {
            "id": str(uuid.uuid4()),
            "preset_id": preset_id,
            "name": prompt.get("name") or identifier,
            "content": prompt.get("content", ""),
            "reasoning": prompt.get("reasoning", ""),
            "role": prompt.get("role", "system"),
            "enabled": int(enabled),
            "position": 0.0,
            "block_type": block_type,
            "injection_depth": prompt.get("injection_depth") if is_in_chat else None,
            "injection_order": prompt.get("injection_order", 0) if is_in_chat else 0,
        }
        block_map[identifier] = block

    seen: set[str] = set()
    for ident in order_list:
        if ident in block_map and ident not in seen:
            blocks_in_order.append(block_map[ident])
            seen.add(ident)
    for prompt in prompts:
        ident = prompt.get("identifier", "")
        if ident not in seen:
            blocks_in_order.append(block_map[ident])
            seen.add(ident)

    pos = 0.0
    for b in blocks_in_order:
        pos += 1.0
        b["position"] = pos
        await db.execute(
            """INSERT INTO preset_blocks
               (id, preset_id, name, content, reasoning, role, enabled, position, block_type, injection_depth, injection_order)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (b["id"], b["preset_id"], b["name"], b["content"], b["reasoning"],
             b["role"], b["enabled"], b["position"], b["block_type"],
             b["injection_depth"], b["injection_order"]),
        )

    return {"id": preset_id, "name": preset_name, "block_count": len(blocks_in_order)}


async def _next_preset_block_position(db: aiosqlite.Connection, preset_id: str) -> float:
    async with db.execute(
        "SELECT COALESCE(MAX(position), -1) FROM preset_blocks WHERE preset_id = ?", (preset_id,)
    ) as cur:
        row = await cur.fetchone()
    return (row[0] if row[0] is not None else -1) + 1


async def create_preset_block(
    db: aiosqlite.Connection,
    preset_id: str,
    name: str,
    content: str = "",
    reasoning: str = "",
    role: str = "system",
    enabled: bool = True,
    block_type: str = "text",
    injection_depth: int | None = None,
    injection_order: int = 0,
) -> dict:
    block_id = str(uuid.uuid4())
    next_pos = await _next_preset_block_position(db, preset_id)
    enabled_int = int(enabled)

    if enabled_int and block_type == "variable":
        group_name = variable_group_name(name)
        async with db.execute(
            "SELECT 1 FROM preset_blocks WHERE preset_id = ? AND block_type = 'variable' "
            "AND enabled = 1 AND (name = ? OR name LIKE ?) LIMIT 1",
            (preset_id, group_name, f"{group_name}:%"),
        ) as cur:
            if await cur.fetchone():
                enabled_int = 0

    await db.execute(
        """INSERT INTO preset_blocks
           (id, preset_id, name, content, reasoning, role, enabled, position, block_type, injection_depth, injection_order)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (block_id, preset_id, name, content, reasoning, role, enabled_int, next_pos,
         block_type, injection_depth, injection_order),
    )
    return {"id": block_id, "position": next_pos}


async def update_preset_block(db: aiosqlite.Connection, preset_id: str, block_id: str, updates: dict) -> None:
    allowed = {"name", "content", "reasoning", "role", "enabled", "position", "injection_depth", "injection_order"}
    updates = {k: v for k, v in updates.items() if k in allowed}
    if not updates:
        return

    if "enabled" in updates and updates["enabled"]:
        async with db.execute(
            "SELECT name, block_type FROM preset_blocks WHERE id = ? AND preset_id = ?",
            (block_id, preset_id),
        ) as cur:
            block_row = await cur.fetchone()
        if block_row and block_row["block_type"] == "variable":
            group_name = variable_group_name(block_row["name"])
            await db.execute(
                "UPDATE preset_blocks SET enabled = 0 WHERE preset_id = ? AND block_type = 'variable' AND id != ? AND (name = ? OR name LIKE ?)",
                (preset_id, block_id, group_name, f"{group_name}:%"),
            )

    cols = ", ".join(f"{k} = ?" for k in updates)
    vals = list(updates.values()) + [block_id, preset_id]
    await db.execute(f"UPDATE preset_blocks SET {cols} WHERE id = ? AND preset_id = ?", vals)


async def replace_preset_blocks(
    db: aiosqlite.Connection, preset_id: str, blocks: list[dict]
) -> None:
    if not blocks:
        return
    block_ids = [b["id"] for b in blocks]
    placeholders = ",".join("?" * len(block_ids))
    async with db.execute(
        f"SELECT id FROM preset_blocks WHERE id IN ({placeholders}) AND preset_id = ?",
        (*block_ids, preset_id),
    ) as cur:
        found = {r["id"] for r in await cur.fetchall()}
    missing = set(block_ids) - found
    if missing:
        from fastapi import HTTPException
        raise HTTPException(400, detail=f"Blocks not found: {missing}")
    for b in blocks:
        await db.execute(
            "UPDATE preset_blocks SET position = ? WHERE id = ? AND preset_id = ?",
            (b["position"], b["id"], preset_id),
        )


async def delete_preset_block(db: aiosqlite.Connection, preset_id: str, block_id: str) -> None:
    await db.execute("DELETE FROM preset_blocks WHERE id = ? AND preset_id = ?", (block_id, preset_id))
