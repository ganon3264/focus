import json
import logging
import sqlite3
from io import BytesIO
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import aiosqlite

from focus.core.models import ExportRequest
from focus.core.paths import ASSETS_DIR, TOOLS_DIR
from focus.core.utils import now_iso
from focus.db.themes import BUILTIN_THEMES
from focus.exchange_remap import PATH_FIELDS, build_id_map, collect_fk_columns, remap_database, remap_path
from focus.exchange_sanitize import (
    MAX_IMPORT_ENTRIES,
    MAX_IMPORT_UNCOMPRESSED_BYTES,
    is_safe_zip_entry,
    sanitize_segments_json,
)
from focus.tools.external import ExternalToolConfig

logger = logging.getLogger("focus.exchange")
FOCUS_VERSION = "0.3.0"
FOCUS_VERSION_PARTS = tuple(int(p) for p in FOCUS_VERSION.split("."))


def _version_tuple(version) -> tuple[int, ...]:
    """Parse an archive version string for comparison; reject garbage."""
    if not isinstance(version, str):
        raise ValueError("Invalid archive version in manifest")
    try:
        return tuple(int(p) for p in version.split("."))
    except ValueError:
        raise ValueError("Invalid archive version in manifest")

# Tables in dependency order for export (must include all FKs before dependents)
EXPORT_TABLES = [
    "characters",
    "personas",
    "presets",
    "providers",
    "secrets",
    "themes",
    "char_blocks",
    "preset_blocks",
    "chats",
    "messages",
    "message_variants",
    "block_images",
    "message_attachments",
    "tool_calls",
    "settings",
]

# Insertion order: parents before children
INSERT_ORDER = [
    "themes",
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
    "tool_calls",
    "settings",
]


def _asset_entry_name(path_str: str) -> str | None:
    """Map a stored file path to an ASSETS_DIR-relative archive entry name.

    Stored paths are cwd-relative (``assets/...``) except tool images, which
    are ASSETS_DIR-relative (``tool/...``).
    """
    candidates = [Path(path_str)]
    if not candidates[0].is_absolute():
        candidates.append(ASSETS_DIR / path_str)
    for cand in candidates:
        try:
            return str(cand.resolve().relative_to(ASSETS_DIR.resolve()))
        except ValueError:
            continue
    return None


async def _resolve_entity_ids(
    db: aiosqlite.Connection,
    table: str,
    selections: list[str],
) -> set[str]:
    if not selections:
        return set()
    if "*" in selections:
        async with db.execute(
            f"SELECT id FROM {table} WHERE is_deleted = 0" if table == "characters" else f"SELECT id FROM {table}"
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
        "tool_calls": await _query_table(db, "tool_calls", "chat_id", chat_ids),
        "themes": [
            t for t in await _query_table_all(db, "themes") if not t["is_system"]
        ],
        "settings": await _query_table_all(db, "settings"),
    }

    # Archives must be self-contained and collision-free: rewrite every id,
    # foreign key, and asset path to fresh values so import can restore
    # verbatim (see import_data).
    raw_database = database
    id_map = build_id_map(database)
    # Built-in themes don't travel with the archive; keep references to them
    # (characters.theme_id) intact so they resolve to the app's own seeded rows.
    for bid in BUILTIN_THEMES:
        id_map.setdefault(bid["id"], bid["id"])
    fk_columns = await collect_fk_columns(db, [t for t in EXPORT_TABLES if t in database])
    database = remap_database(database, id_map, fk_columns, null_unmapped_fks=True, rebase_attachments=True)

    buf = BytesIO()
    with ZipFile(buf, "w", ZIP_DEFLATED) as zf:
        tool_count = 0
        if TOOLS_DIR.is_dir():
            for f in sorted(TOOLS_DIR.iterdir()):
                if f.suffix == ".json" and f.is_file():
                    tool_count += 1

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
                "tool_calls": len(database.get("tool_calls", [])),
                "themes": len(database.get("themes", [])),
                "settings": len(database.get("settings", [])),
                "tools": tool_count,
            },
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
        zf.writestr("database.json", json.dumps(database, indent=2, ensure_ascii=False))

        seen_entries: set[str] = set()
        for table, field in PATH_FIELDS:
            for orig_row, new_row in zip(raw_database.get(table, []), database.get(table, [])):
                old_path = orig_row.get(field)
                new_path = new_row.get(field)
                if not old_path or not new_path:
                    continue
                src = Path(old_path)
                if not src.exists():
                    src2 = ASSETS_DIR / old_path
                    if not src2.exists():
                        continue
                    src = src2
                entry = _asset_entry_name(new_path)
                if entry is None:
                    logger.warning("Skipping file outside assets dir: %s", old_path)
                    continue
                if entry in seen_entries:
                    logger.warning("Duplicate archive entry, skipping: %s", entry)
                    continue
                seen_entries.add(entry)
                zf.write(src, entry)

        if TOOLS_DIR.is_dir():
            for f in sorted(TOOLS_DIR.iterdir()):
                if f.suffix == ".json" and f.is_file():
                    zf.write(f, f"tools/{f.name}")

    return buf.getvalue()


async def _query_table_all(db: aiosqlite.Connection, table: str) -> list[dict]:
    async with db.execute(f"SELECT * FROM {table}") as cur:
        return [dict(r) for r in await cur.fetchall()]


async def import_data(db: aiosqlite.Connection, zip_bytes: bytes) -> dict:
    total_bytes = 0
    created: list[Path] = []
    extracted_dests: set[Path] = set()

    def read_entry(zf: ZipFile, name: str) -> bytes:
        nonlocal total_bytes
        buf = bytearray()
        with zf.open(name) as src:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_IMPORT_UNCOMPRESSED_BYTES:
                    raise ValueError("Archive is too large")
                buf.extend(chunk)
        return bytes(buf)

    def extract_entry(zf: ZipFile, name: str, dest: Path) -> None:
        nonlocal total_bytes
        created.append(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(name) as src, open(dest, "wb") as out:
            while True:
                chunk = src.read(1 << 20)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > MAX_IMPORT_UNCOMPRESSED_BYTES:
                    raise ValueError("Archive is too large")
                out.write(chunk)
        extracted_dests.add(dest)

    with ZipFile(BytesIO(zip_bytes)) as zf:
        names = zf.namelist()
        if len(names) > MAX_IMPORT_ENTRIES:
            raise ValueError("Archive contains too many entries")
        if "manifest.json" not in names or "database.json" not in names:
            raise ValueError("Invalid .focus archive: missing manifest.json or database.json")

        manifest = json.loads(read_entry(zf, "manifest.json"))
        database = json.loads(read_entry(zf, "database.json"))

    if not isinstance(manifest, dict) or not isinstance(database, dict):
        raise ValueError("Invalid .focus archive: bad manifest.json or database.json")
    for table, rows in database.items():
        if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
            raise ValueError(f"Invalid .focus archive: bad rows in table {table!r}")

    if manifest.get("app") != "focus":
        logger.warning("Importing archive from unknown app: %s", manifest.get("app"))

    # Archives before 0.2.0 carried live ids and raw file paths, so import has
    # to re-id them. Newer archives are self-contained (ids, foreign keys and
    # asset paths were rewritten at export time) and are restored verbatim.
    # Compare as version tuples: "0.10.0" must not count as older than "0.2.0".
    legacy = _version_tuple(manifest.get("version", "0.1.0")) < FOCUS_VERSION_PARTS

    if legacy:
        id_map = build_id_map(database)
        fk_columns = await collect_fk_columns(db, [t for t in INSERT_ORDER if t in database])
        remapped = remap_database(database, id_map, fk_columns)
    else:
        id_map = None
        remapped = database

    # Handle provider name collisions (bounded)
    async with db.execute("SELECT name FROM providers") as cur:
        existing_names = {r["name"] for r in await cur.fetchall()}
    for row in remapped.get("providers", []):
        if not isinstance(row.get("name"), str):
            raise ValueError("Invalid provider row in archive")
        original = row["name"]
        counter = 1
        candidate = original
        while candidate in existing_names:
            suffix = " (Imported)" if counter == 1 else f" (Imported {counter})"
            candidate = f"{original}{suffix}"
            counter += 1
        row["name"] = candidate
        existing_names.add(candidate)

    assets_abs = ASSETS_DIR.resolve()
    tools_abs = TOOLS_DIR.resolve()
    legacy_assets_prefix = "assets/"
    asset_subdirs = ("characters/", "attachments/", "blocks/", "personas/", "presets/")

    # Extract files and insert rows inside a single attempt so a failure
    # rolls back the transaction AND removes files written to disk.
    counts: dict[str, int] = {}
    try:
        with ZipFile(BytesIO(zip_bytes)) as zf:
            for name in names:
                if name in ("manifest.json", "database.json") or name.endswith("/"):
                    continue
                if not is_safe_zip_entry(name):
                    raise ValueError(f"Unsafe path in archive: {name!r}")
                if name.startswith("tools/"):
                    rel = Path(name).relative_to("tools")
                    dest = (TOOLS_DIR / rel).resolve()
                    if not dest.is_relative_to(tools_abs):
                        raise ValueError(f"Unsafe path in archive: {name!r}")
                    if dest.suffix != ".json":
                        raise ValueError(f"Non-JSON file in tools/: {name!r}")
                    data = read_entry(zf, name)
                    try:
                        ExternalToolConfig.model_validate(json.loads(data))
                    except Exception as e:
                        raise ValueError(f"Invalid tool config in archive: {name!r}: {e}")
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    created.append(dest)
                    dest.write_bytes(data)
                    continue
                if legacy:
                    if name.startswith("tool/"):
                        rel = Path(remap_path(name, id_map)).relative_to("tool")
                        dest = ASSETS_DIR / "tool" / rel
                    elif name.startswith(legacy_assets_prefix):
                        # Legacy archives stored entries as cwd-relative "assets/..." paths
                        remapped_path = Path(remap_path(name, id_map))
                        rel = Path(*remapped_path.parts[1:]) if len(remapped_path.parts) > 1 else Path(".")
                        dest = ASSETS_DIR / rel
                    elif name.startswith(asset_subdirs):
                        dest = ASSETS_DIR / remap_path(name, id_map)
                    else:
                        logger.warning("Ignoring unknown archive entry: %s", name)
                        continue
                elif name.startswith("tool/") or name.startswith(asset_subdirs):
                    dest = ASSETS_DIR / name
                else:
                    logger.warning("Ignoring unknown archive entry: %s", name)
                    continue
                dest = dest.resolve()
                if not dest.is_relative_to(assets_abs):
                    raise ValueError(f"Unsafe path in archive: {name!r}")
                if not dest.exists() and dest not in extracted_dests:
                    extract_entry(zf, name, dest)

        # Insert rows in dependency order, inside a single transaction
        for table in INSERT_ORDER:
            rows = remapped.get(table, [])
            if not rows:
                counts[table] = 0
                continue
            if table == "secrets":
                for row in rows:
                    if not isinstance(row.get("name"), str) or not isinstance(row.get("value"), str):
                        raise ValueError("Invalid secrets row in archive")
                    await db.execute(
                        "INSERT OR REPLACE INTO secrets (name, value) VALUES (?, ?)",
                        (row["name"], row["value"]),
                    )
                counts[table] = len(rows)
                continue
            if table == "settings":
                # Never clobber the receiving app's live settings; archive
                # values would reference entities from the exporter's DB.
                for row in rows:
                    if not isinstance(row.get("key"), str) or not isinstance(row.get("value"), str):
                        raise ValueError("Invalid settings row in archive")
                    await db.execute(
                        "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                        (row["key"], row["value"]),
                    )
                counts[table] = len(rows)
                continue
            if table == "themes":
                # Built-in themes ship with the app under fixed ids; skip
                # duplicates instead of failing the whole archive.
                for row in rows:
                    if not isinstance(row.get("id"), str) or not isinstance(row.get("name"), str):
                        raise ValueError("Invalid themes row in archive")
                    await db.execute(
                        "INSERT OR IGNORE INTO themes (id, name, colors_json, is_system, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (
                            row["id"],
                            row["name"],
                            row.get("colors_json") or "{}",
                            row.get("is_system") or 0,
                            row.get("created_at") or "",
                        ),
                    )
                counts[table] = len(rows)
                continue

            cols = await db.execute(f"PRAGMA table_info({table})")
            schema_rows = await cols.fetchall()
            valid_columns = {row[1] for row in schema_rows}
            required = {row[1] for row in schema_rows if row[3] and row[4] is None}

            filtered: list[dict] = []
            for row in rows:
                frow = {k: v for k, v in row.items() if k in valid_columns}
                missing = required - frow.keys()
                if missing:
                    raise ValueError(
                        f"Invalid .focus archive: {table} row missing columns: {sorted(missing)}"
                    )
                if table == "message_variants" and "segments_json" in frow:
                    frow["segments_json"] = sanitize_segments_json(frow.get("segments_json"))
                filtered.append(frow)

            columns = list(filtered[0].keys())
            placeholders = ",".join("?" * len(columns))
            colnames = ",".join(columns)
            sql = f"INSERT INTO {table} ({colnames}) VALUES ({placeholders})"
            try:
                for row in filtered:
                    await db.execute(sql, [row.get(c) for c in columns])
            except sqlite3.IntegrityError as e:
                raise ValueError(f"Archive conflicts with existing data: {e}")
            counts[table] = len(filtered)

        await db.commit()
    except Exception:
        await db.rollback()
        for path in created:
            path.unlink(missing_ok=True)
            parent = path.parent
            while parent not in (assets_abs, tools_abs):
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        raise

    summary = {
        "imported": counts,
        "total_entities": sum(counts.values()),
    }
    logger.info("Import complete: %s", summary)
    return summary
