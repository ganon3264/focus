import os
from pathlib import Path

from focus.core.logger import DEBUG_MODE

# Static assets: off by default (browsers revalidate every load, so edits show
# up on a plain refresh). Opt in with FOCUS_CACHE_STATIC=1 for a long immutable
# cache; FOCUS_DEBUG always wins so development never serves stale files.
CACHE_STATIC = not DEBUG_MODE and os.environ.get("FOCUS_CACHE_STATIC", "0").lower() in (
    "1",
    "true",
    "yes",
)

DATA_DIR = Path(os.environ.get("FOCUS_DATA_DIR", "data"))
DB_PATH = DATA_DIR / "focus.db"

ASSETS_DIR = Path(os.environ.get("FOCUS_ASSETS_DIR", "assets"))
CHARACTERS_DIR = ASSETS_DIR / "characters"
PERSONAS_DIR = ASSETS_DIR / "personas"
PRESETS_DIR = ASSETS_DIR / "presets"
ATTACHMENTS_DIR = ASSETS_DIR / "attachments"
COMPRESSED_DIR = ASSETS_DIR / "compressed"
BLOCKS_DIR = ASSETS_DIR / "blocks"
TOOL_ASSETS_DIR = ASSETS_DIR / "tool"

TOOLS_DIR = Path("tools")
EXTENSIONS_DIR = Path("extensions")
