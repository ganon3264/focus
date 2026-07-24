from __future__ import annotations

import shutil
from pathlib import Path

import aiosqlite

from focus.core.paths import (
    ASSETS_DIR,
    CHARACTERS_DIR,
    COMPRESSED_DIR,
    PERSONAS_DIR,
    PRESETS_DIR,
)


async def clean_database(db: aiosqlite.Connection) -> dict:
    """Purge soft-deleted entities and orphaned files. Returns a dict of counts."""
    counts: dict[str, int] = {}

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

    await db.commit()
    await db.execute("VACUUM")
    asset_counts = await clean_orphaned_assets(db)
    counts.update(asset_counts)
    return counts


async def clean_orphaned_assets(db: aiosqlite.Connection) -> dict:
    """Remove every file under ASSETS_DIR not referenced by any DB row.

    This is the "reverse" approach: instead of tracking what was just deleted,
    we query the DB for everything still alive and delete the rest from disk.
    """
    counts: dict[str, int] = {}

    # ── Collect known file paths from DB ──
    known: set[str] = set()

    async with db.execute("SELECT image_path FROM characters WHERE image_path IS NOT NULL") as cur:
        async for row in cur:
            known.add(row["image_path"])

    async with db.execute("SELECT avatar_path FROM personas WHERE avatar_path IS NOT NULL") as cur:
        async for row in cur:
            known.add(row["avatar_path"])

    async with db.execute("SELECT image_path FROM block_images") as cur:
        async for row in cur:
            known.add(row["image_path"])

    async with db.execute("SELECT file_path FROM message_attachments") as cur:
        async for row in cur:
            known.add(row["file_path"])

    # ── Collect valid entity IDs for directory-level decisions ──
    valid_chars: set[str] = {r[0] async for r in await db.execute("SELECT id FROM characters")}
    valid_personas: set[str] = {r[0] async for r in await db.execute("SELECT id FROM personas")}
    valid_presets: set[str] = {r[0] async for r in await db.execute("SELECT id FROM presets")}

    def _is_orphaned_uuid_dir(entry: Path, valid_ids: set[str]) -> bool:
        return entry.is_dir() and len(entry.name) == 36 and entry.name not in valid_ids

    # ── Purge compressed cache (no DB rows ever reference these) ──
    purged = 0
    if COMPRESSED_DIR.exists():
        for f in COMPRESSED_DIR.iterdir():
            if f.is_file():
                f.unlink(missing_ok=True)
                purged += 1
    counts["compressed_purged"] = purged

    # ── Remove orphaned entity directories ──
    orphaned_dirs = 0
    if CHARACTERS_DIR.exists():
        for entry in CHARACTERS_DIR.iterdir():
            if _is_orphaned_uuid_dir(entry, valid_chars):
                shutil.rmtree(entry, ignore_errors=True)
                orphaned_dirs += 1
    if PERSONAS_DIR.exists():
        for entry in PERSONAS_DIR.iterdir():
            if _is_orphaned_uuid_dir(entry, valid_personas):
                shutil.rmtree(entry, ignore_errors=True)
                orphaned_dirs += 1
    if PRESETS_DIR.exists():
        for entry in PRESETS_DIR.iterdir():
            if _is_orphaned_uuid_dir(entry, valid_presets):
                shutil.rmtree(entry, ignore_errors=True)
                orphaned_dirs += 1
    counts["orphaned_entity_dirs"] = orphaned_dirs

    # ── Walk remaining filesystem and delete orphans ──
    orphaned_files = 0
    for entry in ASSETS_DIR.rglob("*"):
        if not entry.is_file():
            continue
        if COMPRESSED_DIR in entry.parents:
            continue
        if str(entry) not in known:
            entry.unlink(missing_ok=True)
            orphaned_files += 1
    counts["orphaned_files"] = orphaned_files

    # ── Remove empty directories bottom-up ──
    empty_dirs = 0
    for entry in sorted(ASSETS_DIR.rglob("*"), key=lambda p: len(str(p)), reverse=True):
        if entry.is_dir():
            try:
                entry.rmdir()
                empty_dirs += 1
            except OSError:
                pass
    counts["empty_dirs_removed"] = empty_dirs

    return counts
