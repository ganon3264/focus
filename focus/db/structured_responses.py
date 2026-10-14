from __future__ import annotations

import uuid

import aiosqlite

from focus.core.utils import now_iso

SCOPES = ("global", "preset")

_FIELDS = ("scope", "scope_id", "name", "json_schema", "template", "enabled")


def _row_to_dict(row: aiosqlite.Row) -> dict:
    response = dict(row)
    response["enabled"] = bool(response["enabled"])
    return response


async def list_responses(
    db: aiosqlite.Connection,
    scope: str | None = None,
    scope_id: str | None = None,
) -> list[dict]:
    """List responses ordered global-first, then by position within each scope."""
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
        f"SELECT * FROM structured_responses {clause} "
        "ORDER BY CASE scope WHEN 'global' THEN 0 ELSE 1 END, position, rowid",
        params,
    ) as cur:
        return [_row_to_dict(r) for r in await cur.fetchall()]


async def get_response(db: aiosqlite.Connection, response_id: str) -> dict | None:
    async with db.execute(
        "SELECT * FROM structured_responses WHERE id = ?", (response_id,)
    ) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row) if row else None


async def _next_position(db: aiosqlite.Connection, scope: str, scope_id: str | None) -> float:
    async with db.execute(
        "SELECT MAX(position) FROM structured_responses WHERE scope = ? AND scope_id IS ?",
        (scope, scope_id),
    ) as cur:
        row = await cur.fetchone()
    return (row[0] if row and row[0] is not None else -1.0) + 1.0


async def _deactivate_scope(
    db: aiosqlite.Connection,
    scope: str,
    scope_id: str | None,
    except_id: str | None = None,
) -> None:
    """Only one response may be active per scope."""
    clause = "scope = ? AND scope_id IS ? AND enabled = 1"
    params: list = [scope, scope_id]
    if except_id is not None:
        clause += " AND id != ?"
        params.append(except_id)
    await db.execute(
        f"UPDATE structured_responses SET enabled = 0, updated_at = ? WHERE {clause}",
        [now_iso(), *params],
    )


async def create_response(db: aiosqlite.Connection, data: dict) -> str:
    response_id = str(uuid.uuid4())
    now = now_iso()
    scope = data.get("scope") or "preset"
    scope_id = data.get("scope_id") if scope == "preset" else None
    enabled = bool(data.get("enabled", True))
    if enabled:
        await _deactivate_scope(db, scope, scope_id)
    await db.execute(
        """INSERT INTO structured_responses
           (id, scope, scope_id, name, json_schema, template, enabled,
            position, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            response_id,
            scope,
            scope_id,
            data.get("name") or "",
            data.get("json_schema") or "",
            data.get("template") or "",
            1 if enabled else 0,
            await _next_position(db, scope, scope_id),
            now,
            now,
        ),
    )
    return response_id


async def update_response(db: aiosqlite.Connection, response_id: str, data: dict) -> None:
    sets = []
    vals: list = []
    for field in _FIELDS:
        if field not in data:
            continue
        value = data[field]
        if field == "enabled":
            value = 1 if value else 0
        elif field == "scope" and value not in SCOPES:
            continue
        if field == "scope_id" and (data.get("scope") or "") == "global":
            value = None
        sets.append(f"{field} = ?")
        vals.append(value)
    if not sets:
        return
    sets.append("updated_at = ?")
    vals.append(now_iso())
    vals.append(response_id)
    await db.execute(
        f"UPDATE structured_responses SET {', '.join(sets)} WHERE id = ?", vals
    )
    if data.get("enabled"):
        current = await get_response(db, response_id)
        if current:
            await _deactivate_scope(
                db, current["scope"], current["scope_id"], except_id=response_id
            )


async def delete_response(db: aiosqlite.Connection, response_id: str) -> None:
    await db.execute("DELETE FROM structured_responses WHERE id = ?", (response_id,))


async def reorder_responses(db: aiosqlite.Connection, ids: list[str]) -> None:
    for index, response_id in enumerate(ids):
        await db.execute(
            "UPDATE structured_responses SET position = ?, updated_at = ? WHERE id = ?",
            (index, now_iso(), response_id),
        )


async def get_active(db: aiosqlite.Connection, preset_id: str | None) -> dict | None:
    """The effective response for a chat: preset-scoped active, else global."""
    if preset_id:
        async with db.execute(
            "SELECT * FROM structured_responses WHERE enabled = 1 AND scope = 'preset' "
            "AND scope_id = ? ORDER BY position, rowid LIMIT 1",
            (preset_id,),
        ) as cur:
            row = await cur.fetchone()
        if row:
            return _row_to_dict(row)
    async with db.execute(
        "SELECT * FROM structured_responses WHERE enabled = 1 AND scope = 'global' "
        "ORDER BY position, rowid LIMIT 1"
    ) as cur:
        row = await cur.fetchone()
    return _row_to_dict(row) if row else None
