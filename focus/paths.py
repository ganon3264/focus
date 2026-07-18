from pathlib import Path
import os

DATA_DIR = Path(os.environ.get("FOCUS_DATA_DIR", "data"))
DB_PATH = DATA_DIR / "focus.db"
BACKUPS_DIR = Path(os.environ.get("FOCUS_BACKUPS_DIR", str(DATA_DIR / "backups")))

ASSETS_DIR = Path("assets")
CHARACTERS_DIR = ASSETS_DIR / "characters"
PERSONAS_DIR = ASSETS_DIR / "personas"
PRESETS_DIR = ASSETS_DIR / "presets"
ATTACHMENTS_DIR = ASSETS_DIR / "attachments"
COMPRESSED_DIR = ATTACHMENTS_DIR / "compressed"
BLOCKS_DIR = ASSETS_DIR / "blocks"
