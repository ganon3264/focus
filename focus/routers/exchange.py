from io import BytesIO

import aiosqlite
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from focus.core.database import get_db
from focus.exchange import export_data, import_data
from focus.core.models import ExportRequest

router = APIRouter()


@router.post("/export")
async def api_export(
    body: ExportRequest,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        zip_bytes = await export_data(db, body)
    except Exception as e:
        raise HTTPException(500, f"Export failed: {e}")

    return StreamingResponse(
        BytesIO(zip_bytes),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=focus-export.focus"},
    )


@router.post("/import", status_code=201)
async def api_import(
    file: UploadFile = File(...),
    db: aiosqlite.Connection = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".focus"):
        raise HTTPException(400, "Only .focus files are accepted")

    zip_bytes = await file.read()
    try:
        result = await import_data(db, zip_bytes)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Import failed: {e}")

    return result
