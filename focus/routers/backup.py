import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from focus.backup import create_backup, delete_backup, list_backups, restore_backup
from focus.core.database import get_db
from focus.core.progress_stream import progress_stream

router = APIRouter()


@router.post("/")
@router.post("")
async def api_create_backup(db: aiosqlite.Connection = Depends(get_db)):
    return progress_stream(lambda progress: create_backup(db, progress=progress))


@router.get("/")
@router.get("")
async def api_list_backups():
    return await list_backups()


@router.post("/{backup_id}/restore")
async def api_restore_backup(
    backup_id: str,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await restore_backup(backup_id, db)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete("/{backup_id}", status_code=204)
async def api_delete_backup(backup_id: str):
    try:
        await delete_backup(backup_id)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
