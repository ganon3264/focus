import os
import aiosqlite

DB_PATH = os.environ.get("PYVERN_DB", "data/pyvern.db")

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS providers (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    base_url    TEXT,
    api_key     TEXT,
    model       TEXT NOT NULL,
    params_json TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS characters (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    image_path  TEXT,
    card_json   TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS char_blocks (
    id           TEXT PRIMARY KEY,
    character_id TEXT NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    content      TEXT NOT NULL DEFAULT '',
    role         TEXT NOT NULL DEFAULT 'system',
    enabled      INTEGER NOT NULL DEFAULT 1,
    position     REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS presets (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preset_blocks (
    id           TEXT PRIMARY KEY,
    preset_id    TEXT NOT NULL REFERENCES presets(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    content      TEXT NOT NULL DEFAULT '',
    role         TEXT NOT NULL DEFAULT 'system',
    enabled      INTEGER NOT NULL DEFAULT 1,
    position     REAL NOT NULL DEFAULT 0,
    is_sentinel  INTEGER NOT NULL DEFAULT 0,
    source       TEXT NOT NULL DEFAULT 'preset',
    character_id TEXT REFERENCES characters(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chats (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT 'New Chat',
    character_id TEXT REFERENCES characters(id) ON DELETE SET NULL,
    preset_id    TEXT REFERENCES presets(id) ON DELETE SET NULL,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id           TEXT PRIMARY KEY,
    chat_id      TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    role         TEXT NOT NULL,
    position     INTEGER NOT NULL,
    active_index INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS message_variants (
    id            TEXT PRIMARY KEY,
    message_id    TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    variant_index INTEGER NOT NULL,
    content       TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_chat_pos     ON messages(chat_id, position);
CREATE INDEX IF NOT EXISTS idx_preset_blocks_pos     ON preset_blocks(preset_id, position);
CREATE INDEX IF NOT EXISTS idx_char_blocks_char      ON char_blocks(character_id, position);
CREATE INDEX IF NOT EXISTS idx_message_variants_msg  ON message_variants(message_id, variant_index);
"""


async def get_db():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db():
    os.makedirs("data", exist_ok=True)
    os.makedirs("avatars", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.commit()
