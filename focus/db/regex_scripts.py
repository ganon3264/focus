from __future__ import annotations

import uuid

import aiosqlite

from focus.core.utils import now_iso

SCOPES = ("global", "preset")
PLACEMENTS = ("user", "ai", "reasoning")

_FIELDS = (
    "scope", "scope_id", "name", "pattern", "replacement", "flags",
    "placement", "apply_prompt", "apply_display", "as_block",
    "enabled", "min_depth", "max_depth",
)


def normalize_placement(raw: str | list[str] | None) -> str:
    """Return a canonical csv of known placements (order-stable, deduped)."""
    if isinstance(raw, list):
        items = raw
    else:
        items = (raw or "").split(",")
    seen = [p for p in PLACEMENTS if p in {i.strip() for i in items}]
    return ",".join(seen)


def _row_to_dict(row: aiosqlite.Row) -> dict:
    script = dict(row)
    for flag in ("enabled", "apply_prompt", "apply_display", "as_block"):
        script[flag] = bool(script[flag])
    return script


async def list_scripts(
    db: aiosqlite.Connection,
    scope: str | None = None,
    scope_id: str | None = None,
) -> list[dict]:
    """List scripts ordered global-first, then by position within each scope."""
    where = []
    params: list = []
    if scope:
        where.append("scope = ?")
        params.append(scope)
    if scope_id is not None:
        where.append("scope_id = ?")
        params.append(scope_id)
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    async with db.execute(
        f"SELECT * FROM regex_scripts {clause} "
        "ORDER BY CASE scope WHEN 'global' THEN 0 ELSE 1 END, position, rowid",
        params,
    ) as cur:
        return [_row_to_dict(r) for r in await cur.fetchall()]


async def get_script(db: aiosqlite.Connection, script_id: str) -> dict | None:
    async with db.execute("SELECT * FROM regex_scripts WHERE id = ?", (script_id,)) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row) if row else None


async def _next_position(db: aiosqlite.Connection, scope: str, scope_id: str | None) -> float:
    async with db.execute(
        "SELECT MAX(position) FROM regex_scripts WHERE scope = ? AND scope_id IS ?",
        (scope, scope_id),
    ) as cur:
        row = await cur.fetchone()
    return (row[0] if row and row[0] is not None else -1.0) + 1.0


async def create_script(db: aiosqlite.Connection, data: dict) -> str:
    script_id = str(uuid.uuid4())
    now = now_iso()
    scope = data.get("scope") or "global"
    scope_id = data.get("scope_id") if scope == "preset" else None
    as_block = bool(data.get("as_block", False))
    # A block lives in the display, so setting one forces display on.
    apply_display = bool(data.get("apply_display", True)) or as_block
    await db.execute(
        """INSERT INTO regex_scripts
           (id, scope, scope_id, name, pattern, replacement, flags, placement,
            apply_prompt, apply_display, as_block, enabled, position, min_depth, max_depth, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            script_id,
            scope,
            scope_id,
            data.get("name") or "",
            data.get("pattern") or "",
            data.get("replacement") or "",
            data.get("flags") or "",
            normalize_placement(data.get("placement")),
            1 if data.get("apply_prompt", True) else 0,
            1 if apply_display else 0,
            1 if as_block else 0,
            1 if data.get("enabled", True) else 0,
            await _next_position(db, scope, scope_id),
            int(data.get("min_depth") or 0),
            int(data["max_depth"]) if data.get("max_depth") is not None else -1,
            now,
            now,
        ),
    )
    return script_id


async def update_script(db: aiosqlite.Connection, script_id: str, data: dict) -> None:
    sets = []
    vals: list = []
    for field in _FIELDS:
        if field not in data:
            continue
        value = data[field]
        # Explicit nulls are ignored (all columns are NOT NULL); scope_id is
        # the one field whose null is meaningful.
        if value is None and field != "scope_id":
            continue
        if field == "placement":
            value = normalize_placement(value)
        elif field in ("enabled", "apply_prompt", "apply_display", "as_block"):
            value = 1 if value else 0
        elif field == "scope":
            if value not in SCOPES:
                continue
        if field == "scope_id" and (data.get("scope") or "") == "global":
            value = None
        sets.append(f"{field} = ?")
        vals.append(value)
    if not sets:
        return
    sets.append("updated_at = ?")
    vals.append(now_iso())
    vals.append(script_id)
    await db.execute(f"UPDATE regex_scripts SET {', '.join(sets)} WHERE id = ?", vals)


async def delete_script(db: aiosqlite.Connection, script_id: str) -> None:
    await db.execute("DELETE FROM regex_scripts WHERE id = ?", (script_id,))


async def reorder_scripts(db: aiosqlite.Connection, ids: list[str]) -> None:
    """Assign positions by index. Callers send ids in display order (globals
    first, then the active preset's), so within-scope order is preserved."""
    for index, script_id in enumerate(ids):
        await db.execute(
            "UPDATE regex_scripts SET position = ?, updated_at = ? WHERE id = ?",
            (index, now_iso(), script_id),
        )


async def resolve(db: aiosqlite.Connection, preset_id: str | None) -> list[dict]:
    """Enabled scripts effective for a chat: global first, then the preset's."""
    async with db.execute(
        "SELECT * FROM regex_scripts WHERE enabled = 1 AND scope = 'global' "
        "ORDER BY position, rowid"
    ) as cur:
        scripts = [_row_to_dict(r) for r in await cur.fetchall()]
    if preset_id:
        async with db.execute(
            "SELECT * FROM regex_scripts WHERE enabled = 1 AND scope = 'preset' "
            "AND scope_id = ? ORDER BY position, rowid",
            (preset_id,),
        ) as cur:
            scripts += [_row_to_dict(r) for r in await cur.fetchall()]
    return scripts


async def resolve_for_chat(db: aiosqlite.Connection, chat_id: str) -> list[dict]:
    async with db.execute("SELECT preset_id FROM chats WHERE id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
    return await resolve(db, row["preset_id"] if row else None)
