import logging
import os
from pathlib import Path

import aiosqlite

from focus.utils import now_iso

logger = logging.getLogger("focus.backup")


def get_backups_dir(backups_root: str | None = None) -> Path:
    if backups_root:
        d = Path(backups_root)
    else:
        d = Path(os.environ.get("FOCUS_BACKUPS_DIR", "data/backups"))
    d.mkdir(parents=True, exist_ok=True)
    return d


async def create_backup(
    db: aiosqlite.Connection,
    *,
    backups_path: str | None = None,
) -> dict:
    from focus.exchange import export_data
    from focus.models import ExportRequest

    req = ExportRequest(
        characters=["*"], personas=["*"], presets=["*"], chats=["*"],
        include_providers=True, include_secrets=True,
    )
    zip_bytes = await export_data(db, req)

    ts = now_iso().replace(":", "-")
    backups_dir = get_backups_dir(backups_path)
    backup_file = backups_dir / f"{ts}.focus"
    backup_file.write_bytes(zip_bytes)

    logger.info("Backup created: %s (%d bytes)", ts, len(zip_bytes))
    return {
        "id": ts,
        "path": str(backup_file),
        "timestamp": now_iso(),
        "size_bytes": len(zip_bytes),
    }


def list_backups(backups_path: str | None = None) -> list[dict]:
    backups_dir = get_backups_dir(backups_path)
    result = []
    if not backups_dir.exists():
        return result
    for entry in sorted(backups_dir.iterdir(), reverse=True):
        if not entry.is_file() or entry.suffix != ".focus":
            continue
        result.append({
            "id": entry.stem,
            "path": str(entry),
            "size_bytes": entry.stat().st_size,
        })
    return result


async def restore_backup(
    backup_id: str,
    db: aiosqlite.Connection,
    *,
    backups_path: str | None = None,
) -> dict:
    from focus.exchange import import_data

    backups_dir = get_backups_dir(backups_path)
    backup_file = backups_dir / f"{backup_id}.focus"
    if not backup_file.is_file():
        raise FileNotFoundError(f"Backup '{backup_id}' not found")

    zip_bytes = backup_file.read_bytes()
    summary = await import_data(db, zip_bytes)

    logger.info("Restored backup '%s': %s", backup_id, summary["imported"])
    return {"restored": True, "backup_id": backup_id, **summary}


def delete_backup(backup_id: str, backups_path: str | None = None) -> None:
    backups_dir = get_backups_dir(backups_path)
    backup_file = backups_dir / f"{backup_id}.focus"
    if not backup_file.is_file():
        raise FileNotFoundError(f"Backup '{backup_id}' not found")
    backup_file.unlink()
    logger.info("Deleted backup '%s'", backup_id)
