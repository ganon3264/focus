import json
import logging
import uuid
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import aiosqlite

from focus.models import ExportRequest
from focus.paths import ASSETS_DIR
from focus.utils import now_iso

logger = logging.getLogger("focus.exchange")
FOCUS_VERSION = "0.1.0"

# Tables in dependency order for export (must include all FKs before dependents)
EXPORT_TABLES = [
    "characters",
    "personas",
    "presets",
    "providers",
    "secrets",
    "char_blocks",
    "preset_blocks",
    "chats",
    "messages",
    "message_variants",
    "block_images",
    "message_attachments",
]

# Insertion order: parents before children
INSERT_ORDER = [
    "characters",
    "personas",
    "presets",
    "providers",
    "secrets",
    "char_blocks",
    "preset_blocks",
    "chats",
    "messages",
    "message_variants",
    "block_images",
    "message_attachments",
]

# Foreign-key remap rules: (table, column, referenced_table)
FK_RULES = [
    ("char_blocks", "character_id", "characters"),
    ("preset_blocks", "preset_id", "presets"),
    ("chats", "character_id", "characters"),
    ("chats", "persona_id", "personas"),
    ("chats", "preset_id", "presets"),
    ("messages", "chat_id", "chats"),
    ("message_variants", "message_id", "messages"),
    ("message_attachments", "chat_id", "chats"),
    ("message_attachments", "message_id", "messages"),
    ("message_attachments", "variant_id", "message_variants"),
    ("block_images", "block_id", "char_blocks"),
    ("block_images", "block_id", "preset_blocks"),
    ("block_images", "block_id", "characters"),
    ("block_images", "block_id", "personas"),
    ("block_images", "block_id", "presets"),
]

PATH_FIELDS = [
    ("characters", "image_path"),
    ("personas", "avatar_path"),
    ("block_images", "image_path"),
    ("message_attachments", "file_path"),
]

def _extract_file_paths(database: dict[str, list[dict]]) -> list[str]:
    paths: list[str] = []
    for table, field in PATH_FIELDS:
        for row in database.get(table, []):
            val = row.get(field)
            if val:
                paths.append(val)
    return paths

def _remap_path(old_path: str, id_map: dict[str, str]) -> str:
    parts = Path(old_path).parts
    new_parts = []
    for part in parts:
        new_parts.append(id_map.get(part, part))
    return str(Path(*new_parts))

def _remap_attachment_path(old_path: str, id_map: dict[str, str]) -> str:
    path = Path(old_path)
    stem = path.stem
    suffix = path.suffix
    new_stem = id_map.get(stem, str(uuid.uuid4()))
    parent = _remap_path(str(path.parent), id_map)
    return str(Path(parent) / f"{new_stem}{suffix}")

def _build_id_map(database: dict[str, list[dict]]) -> dict[str, str]:
    id_map: dict[str, str] = {}
    id_columns = {
        "characters": "id",
        "personas": "id",
        "presets": "id",
        "providers": "id",
        "char_blocks": "id",
        "preset_blocks": "id",
        "chats": "id",
        "messages": "id",
        "message_variants": "id",
        "block_images": "id",
        "message_attachments": "id",
    }
    for table, id_col in id_columns.items():
        for row in database.get(table, []):
            old_id = row.get(id_col)
            if old_id and old_id not in id_map:
                id_map[old_id] = str(uuid.uuid4())
    return id_map

async def _resolve_entity_ids(
    db: aiosqlite.Connection,
    table: str,
    selections: list[str],
) -> set[str]:
    if not selections:
        return set()
    if "*" in selections:
        async with db.execute(
            f"SELECT id FROM {table} WHERE is_deleted = 0"
            if table == "characters"
            else f"SELECT id FROM {table}"
        ) as cur:
            return {r["id"] for r in await cur.fetchall()}
    return set(selections)

async def _query_table(
    db: aiosqlite.Connection,
    table: str,
    where_col: str,
    ids: set[str],
) -> list[dict]:
    if not ids:
        return []
    placeholders = ",".join("?" * len(ids))
    sql = f"SELECT * FROM {table} WHERE {where_col} IN ({placeholders})"
    async with db.execute(sql, list(ids)) as cur:
        return [dict(r) for r in await cur.fetchall()]

async def export_data(db: aiosqlite.Connection, req: ExportRequest) -> bytes:
    char_ids = await _resolve_entity_ids(db, "characters", req.characters)
    persona_ids = await _resolve_entity_ids(db, "personas", req.personas)
    preset_ids = await _resolve_entity_ids(db, "presets", req.presets)
    chat_ids = await _resolve_entity_ids(db, "chats", req.chats)

    # Resolve cascaded references from chats
    if chat_ids:
        placeholders = ",".join("?" * len(chat_ids))
        async with db.execute(
            f"SELECT character_id, persona_id, preset_id FROM chats WHERE id IN ({placeholders})",
            list(chat_ids),
        ) as cur:
            for row in await cur.fetchall():
                if row["character_id"]:
                    char_ids.add(row["character_id"])
                if row["persona_id"]:
                    persona_ids.add(row["persona_id"])
                if row["preset_id"]:
                    preset_ids.add(row["preset_id"])

    # Resolve cascaded references from characters → char_blocks, block_images
    char_block_ids: set[str] = set()
    if char_ids:
        async with db.execute(
            f"SELECT id FROM char_blocks WHERE character_id IN ({','.join('?' * len(char_ids))})",
            list(char_ids),
        ) as cur:
            char_block_ids = {r["id"] for r in await cur.fetchall()}

    # Resolve cascaded from presets → preset_blocks
    preset_block_ids: set[str] = set()
    if preset_ids:
        placeholders = ",".join("?" * len(preset_ids))
        async with db.execute(
            f"SELECT id FROM preset_blocks WHERE preset_id IN ({placeholders})",
            list(preset_ids),
        ) as cur:
            preset_block_ids = {r["id"] for r in await cur.fetchall()}

    # Messages + variants + attachments cascade from chats
    message_ids: set[str] = set()
    if chat_ids:
        placeholders = ",".join("?" * len(chat_ids))
        async with db.execute(
            f"SELECT id FROM messages WHERE chat_id IN ({placeholders})",
            list(chat_ids),
        ) as cur:
            message_ids = {r["id"] for r in await cur.fetchall()}

    variant_ids: set[str] = set()
    if message_ids:
        placeholders = ",".join("?" * len(message_ids))
        async with db.execute(
            f"SELECT id FROM message_variants WHERE message_id IN ({placeholders})",
            list(message_ids),
        ) as cur:
            variant_ids = {r["id"] for r in await cur.fetchall()}

    # Collect all block_images referenced by any entity
    all_block_refs = char_ids | persona_ids | preset_ids | char_block_ids | preset_block_ids
    block_image_ids: set[str] = set()

    # Query block_images where block_id matches any of the above
    block_image_rows: list[dict] = []
    if all_block_refs:
        placeholders = ",".join("?" * len(all_block_refs))
        async with db.execute(
            f"SELECT * FROM block_images WHERE block_id IN ({placeholders})",
            list(all_block_refs),
        ) as cur:
            block_image_rows = [dict(r) for r in await cur.fetchall()]

    # Attachment IDs (cascade from chats + variants)
    attachment_rows: list[dict] = []
    all_attachment_refs = chat_ids | message_ids | variant_ids
    if all_attachment_refs:
        conditions = []
        params: list[str] = []
        if chat_ids:
            conditions.append(f"chat_id IN ({','.join('?' * len(chat_ids))})")
            params.extend(chat_ids)
        if message_ids:
            conditions.append(f"message_id IN ({','.join('?' * len(message_ids))})")
            params.extend(message_ids)
        if variant_ids:
            conditions.append(f"variant_id IN ({','.join('?' * len(variant_ids))})")
            params.extend(variant_ids)
        if conditions:
            async with db.execute(
                f"SELECT * FROM message_attachments WHERE {' OR '.join(conditions)}",
                params,
            ) as cur:
                attachment_rows = [dict(r) for r in await cur.fetchall()]

    # Build the database dump
    database: dict[str, list[dict]] = {
        "characters": await _query_table(db, "characters", "id", char_ids),
        "personas": await _query_table(db, "personas", "id", persona_ids),
        "presets": await _query_table(db, "presets", "id", preset_ids),
        "providers": await _query_table(db, "providers", "id", set())
        if not req.include_providers
        else await _query_table_all(db, "providers"),
        "secrets": await _query_table_all(db, "secrets") if req.include_secrets else [],
        "char_blocks": await _query_table(db, "char_blocks", "id", char_block_ids),
        "preset_blocks": await _query_table(db, "preset_blocks", "id", preset_block_ids),
        "chats": await _query_table(db, "chats", "id", chat_ids),
        "messages": await _query_table(db, "messages", "id", message_ids),
        "message_variants": await _query_table(db, "message_variants", "id", variant_ids),
        "block_images": block_image_rows,
        "message_attachments": attachment_rows,
    }

    if req.include_providers and database["providers"]:
        # providers don't have an is_deleted filter; query all
        pass

    # Collect file paths
    file_paths = _extract_file_paths(database)

    # Build ZIP
    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
        manifest = {
            "app": "focus",
            "version": FOCUS_VERSION,
            "exported_at": now_iso(),
            "entities": {
                "characters": len(database["characters"]),
                "personas": len(database["personas"]),
                "presets": len(database["presets"]),
                "providers": len(database.get("providers", [])),
                "secrets": len(database.get("secrets", [])),
                "char_blocks": len(database["char_blocks"]),
                "preset_blocks": len(database["preset_blocks"]),
                "chats": len(database["chats"]),
                "messages": len(database["messages"]),
                "message_variants": len(database["message_variants"]),
                "block_images": len(database["block_images"]),
                "message_attachments": len(database["message_attachments"]),
            },
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        zf.writestr("database.json", json.dumps(database, indent=2, ensure_ascii=False))

        for path_str in file_paths:
            p = Path(path_str)
            if p.exists():
                zf.write(p, str(p))

    return buf.getvalue()

async def _query_table_all(db: aiosqlite.Connection, table: str) -> list[dict]:
    async with db.execute(f"SELECT * FROM {table}") as cur:
        return [dict(r) for r in await cur.fetchall()]

def _remap_database(
    database: dict[str, list[dict]], id_map: dict[str, str]
) -> dict[str, list[dict]]:
    remapped: dict[str, list[dict]] = {}
    for table, rows in database.items():
        remapped[table] = []
        for row in rows:
            new_row = dict(row)
            # Remap primary key
            for pk_col in ("id", "name"):
                if pk_col in new_row and pk_col != "name":
                    old = new_row[pk_col]
                    if old in id_map:
                        new_row[pk_col] = id_map[old]
            # Don't remap secrets.name — it's the natural PK
            if table == "secrets":
                pass
            remapped[table].append(new_row)

    # Remap foreign keys
    for table, fk_col, _ref_table in FK_RULES:
        if table not in remapped:
            continue
        for row in remapped[table]:
            old = row.get(fk_col)
            if old and old in id_map:
                row[fk_col] = id_map[old]

    # Remap file paths
    for table, field in PATH_FIELDS:
        if table not in remapped:
            continue
        for row in remapped[table]:
            old_path = row.get(field)
            if not old_path:
                continue
            if table == "message_attachments" and field == "file_path":
                row[field] = _remap_attachment_path(old_path, id_map)
            else:
                row[field] = _remap_path(old_path, id_map)

    return remapped

async def import_data(db: aiosqlite.Connection, zip_bytes: bytes) -> dict:
    with ZipFile(BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        if "manifest.json" not in names or "database.json" not in names:
            raise ValueError("Invalid .focus archive: missing manifest.json or database.json")

        manifest = json.loads(zf.read("manifest.json"))
        database = json.loads(zf.read("database.json"))

    # Validate
    if manifest.get("app") != "focus":
        logger.warning("Importing archive from unknown app: %s", manifest.get("app"))

    # Build ID map: all old IDs → new UUIDs
    id_map = _build_id_map(database)

    # Remap all IDs and paths
    remapped = _remap_database(database, id_map)

    # Handle provider name collisions
    async with db.execute("SELECT name FROM providers") as cur:
        existing_names = {r["name"] for r in await cur.fetchall()}
    for row in remapped.get("providers", []):
        original = row["name"]
        while row["name"] in existing_names:
            row["name"] = f"{original} (Imported)"
        existing_names.add(row["name"])

    # Write asset files from ZIP
    with ZipFile(BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            if not name.startswith(str(ASSETS_DIR) + "/"):
                continue
            disk_path = Path(name)  # e.g., assets/characters/{old_id}/avatar.png
            # Remap the path using id_map
            dest = Path(_remap_path(str(disk_path), id_map))
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                dest.write_bytes(zf.read(name))

    # Insert rows in dependency order
    counts: dict[str, int] = {}
    for table in INSERT_ORDER:
        rows = remapped.get(table, [])
        if not rows:
            counts[table] = 0
            continue
        if table == "secrets":
            for row in rows:
                await db.execute(
                    "INSERT OR REPLACE INTO secrets (name, value) VALUES (?, ?)",
                    (row["name"], row["value"]),
                )
            counts[table] = len(rows)
            continue

        # Build column list from first row
        columns = list(rows[0].keys())
        placeholders = ",".join("?" * len(columns))
        colnames = ",".join(columns)
        sql = f"INSERT INTO {table} ({colnames}) VALUES ({placeholders})"
        for row in rows:
            await db.execute(sql, [row[c] for c in columns])
        counts[table] = len(rows)

    await db.commit()

    summary = {
        "imported": counts,
        "total_entities": sum(counts.values()),
    }
    logger.info("Import complete: %s", summary)
    return summary
