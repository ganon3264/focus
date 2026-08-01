import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("FOCUS_DATA_DIR", "data"))
DB_PATH = DATA_DIR / "focus.db"
BACKUPS_DIR = Path(os.environ.get("FOCUS_BACKUPS_DIR", str(DATA_DIR / "backups")))

ASSETS_DIR = Path(os.environ.get("FOCUS_ASSETS_DIR", "assets"))
CHARACTERS_DIR = ASSETS_DIR / "characters"
PERSONAS_DIR = ASSETS_DIR / "personas"
PRESETS_DIR = ASSETS_DIR / "presets"
ATTACHMENTS_DIR = ASSETS_DIR / "attachments"
COMPRESSED_DIR = ASSETS_DIR / "compressed"
BLOCKS_DIR = ASSETS_DIR / "blocks"
TOOL_ASSETS_DIR = ASSETS_DIR / "tool"

TOOLS_DIR = Path("tools")
