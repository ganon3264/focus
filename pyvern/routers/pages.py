from pathlib import Path
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader
import aiosqlite

from pyvern.database import get_db
from pyvern.card_parser import safe_load_card
from pyvern.utils import variable_group_name
from pyvern.macros import build_base_macros, apply_macros
from pyvern.prompt_chain import partition_blocks, resolve_variable_blocks
import pyvern.crud as crud

router = APIRouter()

def _resolve_macros_for_display(messages, char, persona, preset_blocks=None):
    """Apply macros to message content for display resolution (greetings etc.)."""
    if not char:
        return
    card = safe_load_card(char)
    if card is None:
        return
    macros = build_base_macros(card, persona)

    if preset_blocks:
        variables = [b for b in preset_blocks if b["block_type"] == "variable"]
        resolve_variable_blocks(variables, macros)

    for msg in messages:
        if isinstance(msg.get("content"), str):
            msg["content"] = apply_macros(msg["content"], macros)

# Create templates with both directories in search path
templates = Jinja2Templates(directory="templates")
# Extend searchpath so partials/ resolves by name without moving files
if isinstance(templates.env.loader, FileSystemLoader):
    templates.env.loader.searchpath.append(str(Path("partials").resolve()))

@router.get("/chat", response_class=HTMLResponse)
async def chat_redirect(request: Request, character_id: str = Query(None), db: aiosqlite.Connection = Depends(get_db)):
    if character_id:
        async with db.execute("SELECT id FROM chats WHERE character_id = ? AND is_deleted = 0 ORDER BY updated_at DESC LIMIT 1", (character_id,)) as cur:
            row = await cur.fetchone()
        if row:
            return RedirectResponse(url=f"/chat/{row['id']}")
    else:
        async with db.execute("SELECT id FROM chats WHERE is_deleted = 0 ORDER BY updated_at DESC LIMIT 1") as cur:
            row = await cur.fetchone()
        if row:
            return RedirectResponse(url=f"/chat/{row['id']}")

    # If no chat found (either overall, or for the specified character), load the UI in a "chatless" greeter state.
    # To do this, we need to gather the base context (providers, presets, etc) just like a normal chat page.
    character = await crud.get_character(db, character_id)
    presets = await crud.get_presets(db)
    providers = await crud.get_providers(db)
    persona = await crud.get_persona(db)

    # Determine default preset
    preset = presets[0] if presets else None
    preset_blocks = preset["blocks"] if preset else []

    var_blocks, regular_blocks, var_groups = partition_blocks(preset_blocks)

    has_chars = await crud.has_characters(db)

    return templates.TemplateResponse(request, "chat.html", {
        "chat": None,
        "chat_id": None,
        "current_chat_id": None,
        "messages": [],
        "character": character,
        "persona": persona,
        "preset": preset,
        "preset_blocks": regular_blocks,
        "var_groups": var_groups,
        "providers": providers,
        "presets": presets,
        "chats": [],
        "has_characters": has_chars,
        "current_character_id": character_id, # Pre-seed the active character for newChat()
        "current_persona_id": persona["id"] if persona else None,
        "current_preset_id": preset["id"] if preset else None,
    })


@router.get("/chat/{chat_id}", response_class=HTMLResponse)
async def chat_page(request: Request, chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)) as cur:
        chat = await cur.fetchone()
    if not chat:
        return RedirectResponse(url="/chat")
    chat = dict(chat)

    messages = await crud.get_chat_messages(db, chat_id)
    char = await crud.get_character(db, chat.get("character_id"))
    persona = await crud.get_persona(db, chat.get("persona_id"))

    preset = await crud.get_preset(db, chat.get("preset_id"))
    preset_blocks = preset["blocks"] if preset else []
    
    var_blocks, regular_blocks, var_groups = partition_blocks(preset_blocks)
    
    _resolve_macros_for_display(messages, char, persona, preset_blocks)
            
    counts = await crud.get_counts(db, chat.get("character_id"), chat.get("persona_id") or (persona["id"] if persona else None))

    presets = await crud.get_presets(db)
    providers = await crud.get_providers(db)

    # ── Chats for right sidebar ───────────────────────────────────────────────
    chats_sidebar = await crud.get_chats_sidebar(db, chat.get("character_id"))

    has_chars = await crud.has_characters(db)

    return templates.TemplateResponse(request, "chat.html", {
        "chat": chat,
        "chat_id": chat_id,
        "current_chat_id": chat_id,
        "messages": messages,
        "character": char,
        "persona": persona,
        "preset": preset,
        "preset_blocks": regular_blocks,
        "var_groups": var_groups,
        "providers": providers,
        "presets": presets,
        "counts": counts,
        "chats": chats_sidebar,
        "has_characters": has_chars,
        "current_character_id": chat.get("character_id"),
        "current_persona_id": chat.get("persona_id"),
        "current_preset_id": preset["id"] if preset else None,
    })


@router.get("/characters", response_class=HTMLResponse)
async def characters_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    characters = await crud.get_characters(db)
    return templates.TemplateResponse(request, "characters.html", {
        "characters": characters,
    })


@router.get("/presets", response_class=HTMLResponse)
async def presets_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    presets = await crud.get_presets(db)
    
    var_groups = {}
    regular_blocks = []
    if presets:
        _, regular_blocks, var_groups = partition_blocks(presets[0]["blocks"])
        
        # Override the blocks of the first preset to only be regular blocks
        # so the prompt_arranger partial include doesn't duplicate them
        presets[0]["blocks"] = regular_blocks

    return templates.TemplateResponse(request, "presets.html", {
        "presets": presets,
        "var_groups": var_groups,
    })


@router.get("/providers", response_class=HTMLResponse)
async def providers_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    providers = await crud.get_providers(db)
    return templates.TemplateResponse(request, "providers.html", {
        "providers": providers,
    })


@router.get("/personas", response_class=HTMLResponse)
async def personas_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    personas = await crud.get_personas(db)
    return templates.TemplateResponse(request, "personas.html", {
        "personas": personas,
    })


# ── Partials ────────────────────────────────────────────────────────────────

@router.get("/partials/message-list/{chat_id}", response_class=HTMLResponse)
async def message_list_partial(request: Request, chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    messages = await crud.get_chat_messages(db, chat_id)

    char = None
    persona = None
    async with db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)) as cur:
        chat_row = await cur.fetchone()
    if chat_row:
        chat = dict(chat_row)
        char = await crud.get_character(db, chat.get("character_id"))
        persona = await crud.get_persona(db, chat.get("persona_id"))

    _resolve_macros_for_display(messages, char, persona)

    return templates.TemplateResponse(request, "chat/message_list.html", {
        "messages": messages,
        "chat_id": chat_id,
        "character": char,
        "persona": persona,
    })


@router.get("/partials/chat-list", response_class=HTMLResponse)
async def chat_list_partial(
    request: Request,
    character_id: str = Query(None),
    current_chat_id: str = Query(None),
    db: aiosqlite.Connection = Depends(get_db),
):
    chats = await crud.get_chats_sidebar(db, character_id)

    return templates.TemplateResponse(request, "chat/chat_list.html", {
        "chats": chats,
        "current_chat_id": current_chat_id,
    })


@router.get("/partials/char-selector", response_class=HTMLResponse)
async def char_selector_partial(request: Request, chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    characters = await crud.get_characters(db)
    current_character_id = None
    async with db.execute("SELECT character_id FROM chats WHERE id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
        if row:
            current_character_id = row["character_id"]
    return templates.TemplateResponse(request, "chat/char_selector.html", {
        "characters": characters,
        "chat_id": chat_id,
        "current_character_id": current_character_id,
    })


@router.get("/partials/persona-selector", response_class=HTMLResponse)
async def persona_selector_partial(request: Request, chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    personas = await crud.get_personas(db)
    current_persona_id = None
    async with db.execute("SELECT persona_id FROM chats WHERE id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
        if row:
            current_persona_id = row["persona_id"]
    return templates.TemplateResponse(request, "chat/persona_selector.html", {
        "personas": personas,
        "chat_id": chat_id,
        "current_persona_id": current_persona_id,
    })


@router.get("/partials/preset-selector", response_class=HTMLResponse)
async def preset_selector_partial(request: Request, chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    presets = await crud.get_presets(db)
    current_preset_id = None
    async with db.execute("SELECT preset_id FROM chats WHERE id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
        if row:
            current_preset_id = row["preset_id"]
    return templates.TemplateResponse(request, "presets/preset_selector.html", {
        "presets": presets,
        "chat_id": chat_id,
        "current_preset_id": current_preset_id,
    })


@router.get("/partials/preset-variables/{preset_id}", response_class=HTMLResponse)
async def preset_variables_partial(request: Request, preset_id: str, db: aiosqlite.Connection = Depends(get_db)):
    preset = await crud.get_preset(db, preset_id)
    blocks = preset["blocks"] if preset else []
    
    var_groups = {}
    for b in blocks:
        if b["block_type"] == "variable":
            group_name = variable_group_name(b["name"])
            var_groups.setdefault(group_name, []).append(b)

    return templates.TemplateResponse(request, "presets/preset_variables.html", {
        "preset_id": preset_id,
        "var_groups": var_groups
    })

@router.get("/partials/preset-editor/{preset_id}", response_class=HTMLResponse)
async def preset_editor_partial(
    request: Request,
    preset_id: str,
    character_id: str = Query(None),
    persona_id: str = Query(None),
    db: aiosqlite.Connection = Depends(get_db)
):
    preset = await crud.get_preset(db, preset_id)
    blocks = preset["blocks"] if preset else []

    counts = await crud.get_counts(db, character_id or None, persona_id or None)
    _, regular_blocks, var_groups = partition_blocks(blocks)

    return templates.TemplateResponse(request, "presets/preset_editor.html", {
        "blocks": regular_blocks,
        "var_groups": var_groups,
        "preset_id": preset_id,
        "counts": counts
    })

@router.get("/partials/prompt-arranger/{preset_id}", response_class=HTMLResponse)
async def prompt_arranger_partial(
    request: Request,
    preset_id: str,
    character_id: str = Query(None),
    persona_id: str = Query(None),
    db: aiosqlite.Connection = Depends(get_db)
):
    preset = await crud.get_preset(db, preset_id)
    blocks = preset["blocks"] if preset else []

    counts = await crud.get_counts(db, character_id or None, persona_id or None)

    regular_blocks = [b for b in blocks if b["block_type"] != "variable"]

    return templates.TemplateResponse(request, "presets/prompt_arranger.html", {
        "blocks": regular_blocks,
        "preset_id": preset_id,
        "counts": counts
    })


@router.get("/partials/sampler-modal", response_class=HTMLResponse)
async def sampler_modal_partial(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    providers = await crud.get_providers(db)
    return templates.TemplateResponse(request, "modals/sampler_modal.html", {
        "providers": providers,
    })

# ── Modal partials ───────────────────────────────────────────────────────────

@router.get("/partials/providers-modal", response_class=HTMLResponse)
async def providers_modal_partial(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    providers = await crud.get_providers(db)
    
    # Also fetch whether global secrets exist (just boolean presence, never the raw key)
    secrets_present = {}
    async with db.execute("SELECT name FROM secrets") as cur:
        for row in await cur.fetchall():
            secrets_present[row["name"]] = True

    return templates.TemplateResponse(request, "modals/providers_modal.html", {
        "request": request,
        "providers": providers,
        "secrets": secrets_present,
    })


@router.get("/partials/characters-modal", response_class=HTMLResponse)
async def characters_modal_partial(request: Request, current_character_id: str = "", db: aiosqlite.Connection = Depends(get_db)):
    characters = await crud.get_characters(db)
    compact_view = request.cookies.get("pyvern_view_char") == "compact"
    return templates.TemplateResponse(request, "modals/characters_modal.html", {
        "request": request,
        "characters": characters,
        "compact_view": compact_view,
        "current_character_id": current_character_id,
    })


@router.get("/partials/presets-modal", response_class=HTMLResponse)
async def presets_modal_partial(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    presets = await crud.get_presets(db)
    return templates.TemplateResponse(request, "presets/presets_modal.html", {
        "request": request,
        "presets": presets,
    })


@router.get("/partials/personas-modal", response_class=HTMLResponse)
async def personas_modal_partial(request: Request, current_persona_id: str = "", db: aiosqlite.Connection = Depends(get_db)):
    personas = await crud.get_personas(db)
    compact_view = request.cookies.get("pyvern_view_persona") == "compact"
    return templates.TemplateResponse(request, "modals/personas_modal.html", {
        "request": request,
        "personas": personas,
        "compact_view": compact_view,
        "current_persona_id": current_persona_id,
    })

# Add json filter to jinja
def from_json(value):
    import json
    try:
        return json.loads(value)
    except Exception:
        return {}

templates.env.filters["from_json"] = from_json
