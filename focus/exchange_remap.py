"""Identity and file-path remapping for imported .focus archives.

Import assigns fresh UUIDs to every entity and rewrites foreign keys and
asset paths so the imported data never collides with existing rows.

Foreign-key columns are read from the live schema (``PRAGMA
foreign_key_list``) instead of being hardcoded; only columns SQLite cannot
express are listed explicitly.
"""

import uuid
from pathlib import Path

import aiosqlite

# FK columns that are polymorphic (no SQLite REFERENCES clause to derive from)
POLYMORPHIC_FK_COLUMNS = [("block_images", "block_id")]

# Columns that reference files on disk (no schema marker exists)
PATH_FIELDS = [
    ("characters", "image_path"),
    ("personas", "avatar_path"),
    ("block_images", "image_path"),
    ("message_attachments", "file_path"),
    ("tool_calls", "result_image_path"),
]


async def collect_fk_columns(db: aiosqlite.Connection, tables: list[str]) -> dict[str, set[str]]:
    """Map table -> foreign-key columns declared by the live schema."""
    fk_columns: dict[str, set[str]] = {}
    for table in tables:
        columns: set[str] = set()
        async with db.execute("SELECT * FROM pragma_foreign_key_list(?)", (table,)) as cur:
            async for row in cur:
                columns.add(row[3])  # "from": the local FK column
        if columns:
            fk_columns[table] = columns
    for table, column in POLYMORPHIC_FK_COLUMNS:
        fk_columns.setdefault(table, set()).add(column)
    return fk_columns


def build_id_map(database: dict[str, list[dict]]) -> dict[str, str]:
    id_map: dict[str, str] = {}
    for rows in database.values():
        for row in rows:
            old_id = row.get("id")
            if old_id and old_id not in id_map:
                id_map[old_id] = str(uuid.uuid4())
    return id_map


def remap_path(old_path: str, id_map: dict[str, str]) -> str:
    """Remap path parts that are (or are derived from) archive row ids.

    A path part matches when the whole part is in *id_map* (directory ids
    like ``assets/characters/<id>/``) or when its file stem is (attachment
    files like ``assets/attachments/<id>.png``).  This keeps zip-entry
    extraction and remapped DB rows pointing at the same files.
    """
    parts = Path(old_path).parts
    new_parts = []
    for part in parts:
        mapped = id_map.get(part)
        if mapped is None:
            mapped = id_map.get(Path(part).stem)
        new_parts.append(mapped if mapped is not None else part)
    return str(Path(*new_parts))


def remap_database(
    database: dict[str, list[dict]],
    id_map: dict[str, str],
    fk_columns: dict[str, set[str]],
    null_unmapped_fks: bool = False,
    rebase_attachments: bool = False,
) -> dict[str, list[dict]]:
    remapped: dict[str, list[dict]] = {}
    for table, rows in database.items():
        remapped[table] = []
        for row in rows:
            new_row = dict(row)
            old_id = new_row.get("id")
            if old_id in id_map:
                new_row["id"] = id_map[old_id]
            remapped[table].append(new_row)

    # Remap foreign keys
    for table, columns in fk_columns.items():
        if table not in remapped:
            continue
        for row in remapped[table]:
            for fk_col in columns:
                old = row.get(fk_col)
                if old and old in id_map:
                    row[fk_col] = id_map[old]
                elif null_unmapped_fks:
                    row[fk_col] = None

    # Remap file paths
    for table, field in PATH_FIELDS:
        if table == "message_attachments" and rebase_attachments:
            continue
        if table not in remapped:
            continue
        for row in remapped[table]:
            old_path = row.get(field)
            if not old_path:
                continue
            row[field] = remap_path(old_path, id_map)

    # Attachment rows may share a file on disk (variants/duplicated chats copy
    # file_path verbatim). Rebase each row onto its own remapped id so every
    # row maps to a distinct archive entry and a distinct file after import.
    if rebase_attachments and "message_attachments" in remapped:
        for row in remapped["message_attachments"]:
            old_path = row.get("file_path")
            if not old_path:
                continue
            suffix = Path(old_path).suffix or ".bin"
            row["file_path"] = str(Path(old_path).parent / f"{row['id']}{suffix}")

    return remapped
