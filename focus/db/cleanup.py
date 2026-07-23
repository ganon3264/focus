from __future__ import annotations

import shutil
from pathlib import Path

import aiosqlite

from focus.core.paths import CHARACTERS_DIR, PERSONAS_DIR


async def clean_database(db: aiosqlite.Connection) -> dict:
    """Purge soft-deleted entities and orphaned files. Returns a dict of counts."""
    counts = {}

    deleted_char_ids = {r[0] async for r in await db.execute(
        "SELECT id FROM characters WHERE is_deleted = 1"
    )}
    deleted_persona_ids = {r[0] async for r in await db.execute(
        "SELECT id FROM personas WHERE is_deleted = 1"
    )}

    counts["chats"] = (
        await db.execute(
            "DELETE FROM chats WHERE is_deleted = 1 OR character_id IN (SELECT id FROM characters WHERE is_deleted = 1)"
        )
    ).rowcount

    counts["characters"] = (
        await db.execute("DELETE FROM characters WHERE is_deleted = 1")
    ).rowcount

    counts["personas"] = (
        await db.execute("DELETE FROM personas WHERE is_deleted = 1")
    ).rowcount

    counts["block_images"] = (
        await db.execute("""
            DELETE FROM block_images WHERE block_id NOT IN (
                SELECT id FROM preset_blocks
            ) AND block_id NOT IN (
                SELECT id FROM char_blocks
            ) AND block_id NOT IN (
                SELECT id FROM characters
            ) AND block_id NOT IN (
                SELECT id FROM personas
            )
        """)
    ).rowcount

    counts["attachments"] = (
        await db.execute("DELETE FROM message_attachments WHERE message_id IS NULL")
    ).rowcount

    dirs_purged = 0
    for char_id in deleted_char_ids:
        char_dir = CHARACTERS_DIR / char_id
        if char_dir.exists():
            shutil.rmtree(char_dir, ignore_errors=True)
            dirs_purged += 1
    counts["char_dirs_purged"] = dirs_purged

    dirs_purged = 0
    for persona_id in deleted_persona_ids:
        persona_dir = PERSONAS_DIR / persona_id
        if persona_dir.exists():
            shutil.rmtree(persona_dir, ignore_errors=True)
            dirs_purged += 1
    counts["persona_dirs_purged"] = dirs_purged

    orphaned_dirs = 0
    if CHARACTERS_DIR.exists():
        for entry in CHARACTERS_DIR.iterdir():
            if entry.is_dir() and len(entry.name) == 36:
                async with db.execute("SELECT 1 FROM characters WHERE id = ?", (entry.name,)) as cur:
                    if not await cur.fetchone():
                        shutil.rmtree(entry, ignore_errors=True)
                        orphaned_dirs += 1
    if PERSONAS_DIR.exists():
        for entry in PERSONAS_DIR.iterdir():
            if entry.is_dir() and len(entry.name) == 36:
                async with db.execute("SELECT 1 FROM personas WHERE id = ?", (entry.name,)) as cur:
                    if not await cur.fetchone():
                        shutil.rmtree(entry, ignore_errors=True)
                        orphaned_dirs += 1
    counts["orphaned_dirs_purged"] = orphaned_dirs

    nested = Path("assets") / "assets"
    if nested.exists():
        shutil.rmtree(nested, ignore_errors=True)
        counts["nested_assets_purged"] = 1

    await db.execute("VACUUM")
    return counts
