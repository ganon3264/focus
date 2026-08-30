from __future__ import annotations

import json
import logging
import shlex
from pathlib import Path

from focus.core.paths import EXTENSIONS_DIR
from focus.extensions import ExtensionSpec

logger = logging.getLogger("focus.extensions.loader")

MAX_DEPTH = 2
_cache: list[ExtensionSpec] | None = None


def _parse_command(command: str | list[str]) -> list[str]:
    if isinstance(command, str):
        return shlex.split(command)
    return command


def _load_single(spec_path: Path) -> ExtensionSpec:
    return ExtensionSpec.model_validate(json.loads(spec_path.read_text(encoding="utf-8")))


def load_extensions(directory: Path | None = None) -> list[ExtensionSpec]:
    """Scan ``extensions/`` (recursive, 2 levels, skip hidden) for ``*.json`` specs.

    Returns valid ExtensionSpec objects; malformed files are skipped with a
    warning, exactly like external tools.
    """
    d = directory or EXTENSIONS_DIR
    if not d.is_dir():
        return []

    specs: list[ExtensionSpec] = []
    for f in sorted(d.rglob("*.json")):
        if not f.is_file():
            continue
        rel = f.relative_to(d)
        if len(rel.parents) > MAX_DEPTH:
            continue
        if any(p.name.startswith(".") for p in rel.parents):
            continue
        try:
            specs.append(_load_single(f))
        except Exception as exc:
            logger.warning("Skipping extension %s: %s", f.name, exc)
    return specs


def get_all_extensions() -> list[ExtensionSpec]:
    global _cache
    if _cache is None:
        _cache = load_extensions()
    return list(_cache)


def reload_extensions() -> list[ExtensionSpec]:
    global _cache
    _cache = load_extensions()
    return list(_cache)


def find_extension(name: str) -> ExtensionSpec | None:
    for spec in get_all_extensions():
        if spec.name == name:
            return spec
    return None
