from __future__ import annotations

from typing import Any

from aiosqlite import Connection
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

import focus.db.structured_responses as structured_db
from focus.core.database import get_db
from focus.core.models import (
    StructuredReorder,
    StructuredResponseCreate,
    StructuredResponseUpdate,
)
from focus.core.structured import (
    parse_structured,
    render_structured,
    validate_schema_text,
    validate_template,
)

router = APIRouter()


class StructuredPreview(BaseModel):
    template: str = ""
    json_sample: str = ""


def _validate(data: dict[str, Any]) -> None:
    if "scope" in data and data["scope"] not in structured_db.SCOPES:
        raise HTTPException(400, f"scope must be one of {structured_db.SCOPES}")
    schema_text = data.get("json_schema")
    if schema_text:
        error = validate_schema_text(schema_text)
        if error:
            raise HTTPException(400, f"Invalid JSON schema: {error}")
    template = data.get("template")
    if template:
        error = validate_template(template)
        if error:
            raise HTTPException(400, error)


def _validate_scope_invariant(data: dict[str, Any], existing: dict[str, Any]) -> None:
    """PATCH may move a row between scopes; keep scope_id consistent so the
    single-active checks and export queries never see stale ids."""
    merged_scope = data.get("scope", existing.get("scope"))
    if merged_scope == "global":
        data["scope_id"] = None
    elif not (data.get("scope_id") or existing.get("scope_id")):
        raise HTTPException(400, "scope_id is required for preset-scoped responses")


@router.get("/structured-responses")
async def list_structured_responses(
    preset_id: str | None = Query(None),
    scope: str | None = Query(None),
    scope_id: str | None = Query(None),
    db: Connection = Depends(get_db),
):
    if preset_id is not None:
        responses = await structured_db.list_responses(db, scope="global")
        responses += await structured_db.list_responses(db, scope="preset", scope_id=preset_id)
    else:
        responses = await structured_db.list_responses(db, scope=scope, scope_id=scope_id)
    return {"responses": responses, "preset_id": preset_id}


@router.post("/structured-responses", status_code=201)
async def create_structured_response(
    body: StructuredResponseCreate, db: Connection = Depends(get_db)
):
    data = body.model_dump()
    if data["scope"] == "preset" and not data.get("scope_id"):
        raise HTTPException(400, "scope_id is required for preset-scoped responses")
    _validate(data)
    response_id = await structured_db.create_response(db, data)
    await db.commit()
    return await structured_db.get_response(db, response_id)


@router.patch("/structured-responses/{response_id}")
async def update_structured_response(
    response_id: str, body: StructuredResponseUpdate, db: Connection = Depends(get_db)
):
    existing = await structured_db.get_response(db, response_id)
    if not existing:
        raise HTTPException(404, "Structured response not found")
    data = body.model_dump(exclude_unset=True)
    _validate({**existing, **data})
    _validate_scope_invariant(data, existing)
    await structured_db.update_response(db, response_id, data)
    await db.commit()
    return await structured_db.get_response(db, response_id)


@router.delete("/structured-responses/{response_id}", status_code=204)
async def delete_structured_response(response_id: str, db: Connection = Depends(get_db)):
    if not await structured_db.get_response(db, response_id):
        raise HTTPException(404, "Structured response not found")
    await structured_db.delete_response(db, response_id)
    await db.commit()


@router.post("/structured-responses/reorder")
async def reorder_structured_responses(
    body: StructuredReorder, db: Connection = Depends(get_db)
):
    await structured_db.reorder_responses(db, body.ids)
    await db.commit()
    return {"ok": True}


@router.post("/structured-responses/preview")
async def preview_structured_response(body: StructuredPreview):
    error = validate_template(body.template)
    if error:
        raise HTTPException(400, error)
    data = parse_structured(body.json_sample)
    if data is None:
        raise HTTPException(400, "Sample is not valid JSON")
    try:
        result = render_structured(body.json_sample, body.template, {})
    except Exception as e:
        raise HTTPException(400, str(e))
    return {"result": result}
