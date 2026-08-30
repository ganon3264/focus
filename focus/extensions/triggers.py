from __future__ import annotations

import asyncio
import logging

import aiosqlite

from focus.core.paths import DB_PATH
from focus.db.extensions import get_chat_states
from focus.extensions.loader import get_all_extensions
from focus.extensions.runner import apply_actions, build_envelope, run_extension

logger = logging.getLogger("focus.extensions.triggers")


async def _db_path(db: aiosqlite.Connection) -> str:
    """Resolve the backing database file from a (possibly overridden) connection."""
    try:
        async with db.execute("PRAGMA database_list") as cur:
            row = await cur.fetchone()
        if row and row[2]:
            return row[2]
    except Exception:
        logger.debug("Could not resolve DB path from connection; falling back to DB_PATH")
    return str(DB_PATH)


async def _trigger_specs_for(conn: aiosqlite.Connection, chat_id: str, event: str):
    """Enabled extensions for *chat_id* whose ``triggers`` include *event*."""
    states = await get_chat_states(conn, chat_id)
    return [spec for spec in get_all_extensions() if states.get(spec.name, False) and event in spec.triggers]


async def _run_trigger(path: str, chat_id: str, event: str, message_id: str) -> None:
    """Run every enabled extension subscribed to *event* on *message_id*.

    Opens its own connection (fire-and-forget, survives the request scope) and
    ignores per-extension failures so one bad script can't break the others.
    """
    try:
        async with aiosqlite.connect(path) as conn:
            conn.row_factory = aiosqlite.Row
            await conn.execute("PRAGMA foreign_keys=ON")
            specs = await _trigger_specs_for(conn, chat_id, event)
            for spec in specs:
                try:
                    envelope, target, chat = await build_envelope(conn, spec, chat_id, message_id)
                    if target["role"] not in spec.roles:
                        continue
                    result = await run_extension(spec, envelope)
                    summary = await apply_actions(conn, spec, result, chat, target)
                    await conn.commit()
                    logger.info(
                        "trigger[%s] %s -> %s (status=%s)", event, spec.name, message_id, summary["status"],
                    )
                except Exception:
                    logger.exception("trigger[%s] %s on %s failed", event, spec.name, message_id)
    except Exception:
        logger.exception("trigger[%s] failed for chat=%s msg=%s", event, chat_id, message_id)


async def schedule_trigger(db: aiosqlite.Connection, chat_id: str, event: str, message_id: str) -> None:
    """Fire-and-forget dispatch of *event* for *chat_id*/*message_id*.

    Never blocks the caller — spawns a background task on its own connection.
    """
    path = await _db_path(db)
    asyncio.get_running_loop().create_task(_run_trigger(path, chat_id, event, message_id))


async def run_trigger_sync(db: aiosqlite.Connection, chat_id: str, event: str, message_id: str) -> list[dict]:
    """Run every enabled extension subscribed to *event* on *message_id*, awaited.

    Unlike ``schedule_trigger`` this blocks the caller until each extension
    finishes, returning its summary. Used by the stream path so a ``generation_end``
    rewrite can land *before* ``done`` — making the reply finalize as the rewrite
    and letting the result surface to the client as SSE events for toasts.

    Runs on the *provided* connection (the caller's request DB, which is still
    valid inside the generator). A failure in one extension doesn't stop the rest;
    it becomes an ``error`` summary so the client gets a toast either way.
    """
    specs = await _trigger_specs_for(db, chat_id, event)
    summaries: list[dict] = []
    for spec in specs:
        try:
            envelope, target, chat = await build_envelope(db, spec, chat_id, message_id)
            if target["role"] not in spec.roles:
                continue
            result = await run_extension(spec, envelope)
            summary = await apply_actions(db, spec, result, chat, target)
            await db.commit()  # edit_message_create_variant / create_attachment don't commit
            summary["extension"] = spec.name
            summaries.append(summary)
        except Exception as e:
            logger.exception("trigger[%s] %s on %s failed", event, spec.name, message_id)
            summaries.append({
                "extension": spec.name, "status": "error", "error": str(e),
                "logs": [], "content": None,
            })
    return summaries
