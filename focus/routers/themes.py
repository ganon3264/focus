from fastapi import APIRouter, Depends, HTTPException

import focus.db.themes as db_themes
from focus.core.database import get_db
from focus.core.models import ThemeCreate, ThemeUpdate

router = APIRouter()


@router.get("/")
@router.get("")
async def list_themes(_db=Depends(get_db)):
    return await db_themes.list_themes(_db)


@router.post("/", status_code=201)
@router.post("", status_code=201)
async def create_theme(body: ThemeCreate, _db=Depends(get_db)):
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Theme name is required")
    theme_id = await db_themes.create_theme(_db, name, body.colors)
    await _db.commit()
    return {"id": theme_id, "name": name}


@router.patch("/{theme_id}")
async def update_theme(theme_id: str, body: ThemeUpdate, _db=Depends(get_db)):
    theme = await db_themes.get_theme(_db, theme_id)
    if not theme:
        raise HTTPException(404, "Theme not found")
    fields = body.model_fields_set
    await db_themes.update_theme(
        _db,
        theme_id,
        name=body.name if "name" in fields and body.name is not None else db_themes.UNSET,
        colors=body.colors if "colors" in fields and body.colors is not None else db_themes.UNSET,
    )
    await _db.commit()
    return {"ok": True}


@router.post("/{theme_id}/reset")
async def reset_theme(theme_id: str, _db=Depends(get_db)):
    theme = await db_themes.get_theme(_db, theme_id)
    if not theme:
        raise HTTPException(404, "Theme not found")
    if not theme["is_system"]:
        raise HTTPException(409, "Only built-in themes can be reset")
    await db_themes.reset_theme(_db, theme_id)
    await _db.commit()
    return {"ok": True}


@router.delete("/{theme_id}", status_code=204)
async def delete_theme(theme_id: str, _db=Depends(get_db)):
    theme = await db_themes.get_theme(_db, theme_id)
    if not theme:
        raise HTTPException(404, "Theme not found")
    if theme["is_system"]:
        raise HTTPException(409, "Built-in themes cannot be deleted")
    await db_themes.delete_theme(_db, theme_id)
    if await db_themes.get_setting(_db, db_themes.DARK_SLOT_KEY) == theme_id:
        await db_themes.set_setting(_db, db_themes.DARK_SLOT_KEY, db_themes.BUILTIN_SLATE_ID)
    if await db_themes.get_setting(_db, db_themes.LIGHT_SLOT_KEY) == theme_id:
        await db_themes.set_setting(_db, db_themes.LIGHT_SLOT_KEY, db_themes.BUILTIN_LIGHT_ID)
    await _db.commit()
