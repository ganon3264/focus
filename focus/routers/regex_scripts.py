from __future__ import annotations

import asyncio
import re
from typing import Any

from aiosqlite import Connection
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import focus.db.regex_scripts as regex_db
from focus.core.database import get_db
from focus.core.models import RegexReorder, RegexScriptCreate, RegexScriptUpdate
from focus.core.regex_scripts import (
    MAX_INPUT_LENGTH,
    REGEX_TIMEOUT,
    compile_pattern,
    preview_transform,
    validate_pattern,
)

router = APIRouter()


class RegexPreview(BaseModel):
    pattern: str = ""
    replacement: str = ""
    flags: str = ""
    sample: str = ""
    as_block: bool = False
    name: str = "Block"


def _validate(data: dict[str, Any]) -> None:
    if "scope" in data and data["scope"] not in regex_db.SCOPES:
        raise HTTPException(400, f"scope must be one of {regex_db.SCOPES}")
    if "placement" in data:
        normalized = regex_db.normalize_placement(data["placement"])
        if not normalized:
            raise HTTPException(400, "placement must include at least one of user, ai, reasoning")
        data["placement"] = normalized
    pattern = data.get("pattern")
    if pattern:
        flags = data.get("flags") or ""
        error = validate_pattern(pattern, flags)
        if error:
            raise HTTPException(400, f"Invalid pattern: {error}")
        replacement = data.get("replacement")
        if replacement is not None:
            compiled = compile_pattern(pattern, flags)
            if compiled is None:
                raise HTTPException(400, "Invalid pattern")
            try:
                compiled.sub(replacement, "")
            except re.error as e:
                raise HTTPException(400, f"Invalid replacement: {e}")


def _validate_scope_invariant(data: dict[str, Any], existing: dict[str, Any]) -> None:
    """PATCH may move a row between scopes; keep scope_id consistent so the
    single-active checks and export queries never see stale ids."""
    merged_scope = data.get("scope", existing.get("scope"))
    if merged_scope == "global":
        data["scope_id"] = None
    elif not (data.get("scope_id") or existing.get("scope_id")):
        raise HTTPException(400, "scope_id is required for preset-scoped scripts")


@router.get("/regex-scripts")
async def list_regex_scripts(
    preset_id: str | None = Query(None),
    scope: str | None = Query(None),
    scope_id: str | None = Query(None),
    db: Connection = Depends(get_db),
):
    """Effective editable set: global scripts plus, when *preset_id* is given,
    that preset's scripts."""
    if preset_id is not None:
        scripts = await regex_db.list_scripts(db, scope="global")
        scripts += await regex_db.list_scripts(db, scope="preset", scope_id=preset_id)
    else:
        scripts = await regex_db.list_scripts(db, scope=scope, scope_id=scope_id)
    return {"scripts": scripts, "preset_id": preset_id}


@router.post("/regex-scripts", status_code=201)
async def create_regex_script(body: RegexScriptCreate, db: Connection = Depends(get_db)):
    data = body.model_dump()
    if data["scope"] == "preset" and not data.get("scope_id"):
        raise HTTPException(400, "scope_id is required for preset-scoped scripts")
    _validate(data)
    script_id = await regex_db.create_script(db, data)
    await db.commit()
    return await regex_db.get_script(db, script_id)


@router.patch("/regex-scripts/{script_id}")
async def update_regex_script(
    script_id: str, body: RegexScriptUpdate, db: Connection = Depends(get_db)
):
    existing = await regex_db.get_script(db, script_id)
    if not existing:
        raise HTTPException(404, "Regex script not found")
    data = body.model_dump(exclude_unset=True)
    # Validate against the merged result so a replacement can be checked against
    # unchanged pattern/flags too.
    merged = {**existing, **data}
    _validate(merged)
    _validate_scope_invariant(data, existing)
    # A block lives in the display, so it keeps display on.
    if merged.get("as_block"):
        data["apply_display"] = True
    await regex_db.update_script(db, script_id, data)
    await db.commit()
    return await regex_db.get_script(db, script_id)


@router.delete("/regex-scripts/{script_id}", status_code=204)
async def delete_regex_script(script_id: str, db: Connection = Depends(get_db)):
    if not await regex_db.get_script(db, script_id):
        raise HTTPException(404, "Regex script not found")
    await regex_db.delete_script(db, script_id)
    await db.commit()


@router.post("/regex-scripts/reorder")
async def reorder_regex_scripts(body: RegexReorder, db: Connection = Depends(get_db)):
    await regex_db.reorder_scripts(db, body.ids)
    await db.commit()
    return {"ok": True}


@router.post("/regex-scripts/preview")
async def preview_regex_script(body: RegexPreview):
    error = validate_pattern(body.pattern, body.flags)
    if error:
        raise HTTPException(400, f"Invalid pattern: {error}")
    # User-supplied sample: run off the event loop with the same wall-clock cap
    # as the generation path so a pathological pattern cannot hang the server.
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                preview_transform,
                body.pattern,
                body.replacement,
                body.flags,
                body.sample[:MAX_INPUT_LENGTH],
                as_block=body.as_block,
                name=body.name,
            ),
            timeout=REGEX_TIMEOUT,
        )
    except asyncio.TimeoutError:
        raise HTTPException(400, "Pattern too slow on that sample")
    except (ValueError, re.error) as e:
        raise HTTPException(400, f"Invalid replacement: {e}")
    return {"result": result}
