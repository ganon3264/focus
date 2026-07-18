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

CREATE TABLE IF NOT EXISTS personas (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    avatar_path TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS preset_blocks (
    id           TEXT PRIMARY KEY,
    preset_id    TEXT NOT NULL REFERENCES presets(id) ON DELETE CASCADE,
    name         TEXT NOT NULL,
    content      TEXT NOT NULL DEFAULT '',
    role         TEXT NOT NULL DEFAULT 'system',
    enabled      INTEGER NOT NULL DEFAULT 1,
    position     REAL NOT NULL DEFAULT 0,
    block_type   TEXT NOT NULL DEFAULT 'text'
    -- block_type: text | chat_history | char_description | char_personality | char_blocks | user_persona
);

CREATE TABLE IF NOT EXISTS chats (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL DEFAULT 'New Chat',
    character_id TEXT REFERENCES characters(id) ON DELETE SET NULL,
    persona_id   TEXT REFERENCES personas(id) ON DELETE SET NULL,
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

CREATE TABLE IF NOT EXISTS block_images (
    id           TEXT PRIMARY KEY,
    block_id     TEXT NOT NULL,
    block_source TEXT NOT NULL DEFAULT 'preset',  -- 'preset' | 'char'
    image_path   TEXT NOT NULL,
    mime_type    TEXT NOT NULL DEFAULT 'image/png',
    position     INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS secrets (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_block_images_block ON block_images(block_id, position);

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
    os.makedirs("assets/characters", exist_ok=True)
    os.makedirs("assets/personas", exist_ok=True)
    os.makedirs("assets/presets", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        # Seed default persona if none exist
        async with db.execute("SELECT COUNT(*) FROM personas") as cur:
            count = (await cur.fetchone())[0]
        if count == 0:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            import uuid
            await db.execute(
                "INSERT INTO personas (id, name, description, avatar_path, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), "User", "", None, now),
            )
        await db.commit()
