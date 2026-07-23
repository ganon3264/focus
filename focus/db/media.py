from __future__ import annotations

import uuid
from pathlib import Path

import aiosqlite

from focus.core.utils import SUFFIX_MIME_MAP, SUFFIX_MIME_MAP_IMAGES_ONLY, now_iso


async def next_position(db: aiosqlite.Connection, table: str, where_col: str, where_val: str) -> int:
    async with db.execute(
        f"SELECT COALESCE(MAX(position), -1) FROM {table} WHERE {where_col} = ?", (where_val,)
    ) as cur:
        row = await cur.fetchone()
    return row[0] + 1


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
