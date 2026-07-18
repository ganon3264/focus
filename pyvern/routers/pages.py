import json
from pathlib import Path
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from jinja2 import FileSystemLoader
import aiosqlite

from pyvern.database import get_db

router = APIRouter()

# Create templates with both directories in search path
templates = Jinja2Templates(directory="templates")
# Extend searchpath so partials/ resolves by name without moving files
if isinstance(templates.env.loader, FileSystemLoader):
    templates.env.loader.searchpath.append(str(Path("partials").resolve()))


@router.get("/chat", response_class=HTMLResponse)
async def chat_redirect(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT id FROM chats ORDER BY updated_at DESC LIMIT 1") as cur:
        row = await cur.fetchone()
    if row:
        return RedirectResponse(url=f"/chat/{row['id']}")
    return HTMLResponse("""<div class="p-3">No chats yet. <a href="/characters" style="color:var(--accent)">Create a character and start chatting</a></div>""")


@router.get("/chat/{chat_id}", response_class=HTMLResponse)
async def chat_page(request: Request, chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)) as cur:
        chat = await cur.fetchone()
    if not chat:
        return HTMLResponse("Chat not found", status_code=404)
    chat = dict(chat)

    async with db.execute("""
        SELECT m.id, m.role, m.position, m.active_index, mv.content, mv.variant_index,
               (SELECT COUNT(*) FROM message_variants WHERE message_id = m.id) as variant_count
        FROM messages m
        JOIN message_variants mv ON mv.message_id = m.id AND mv.variant_index = m.active_index
        WHERE m.chat_id = ?
        ORDER BY m.position
    """, (chat_id,)) as cur:
        messages = [dict(r) for r in await cur.fetchall()]

    char = None
    if chat.get("character_id"):
        async with db.execute("SELECT * FROM characters WHERE id = ?", (chat["character_id"],)) as cur:
            char_row = await cur.fetchone()
        if char_row:
            char = dict(char_row)
            try:
                char["card"] = json.loads(char_row["card_json"] or "{}")
            except Exception:
                char["card"] = {}

    persona = None
    if chat.get("persona_id"):
        async with db.execute("SELECT * FROM personas WHERE id = ?", (chat["persona_id"],)) as cur:
            row = await cur.fetchone()
            if row:
                persona = dict(row)
    if not persona:
        async with db.execute("SELECT * FROM personas ORDER BY created_at LIMIT 1") as cur:
            row = await cur.fetchone()
            if row:
                persona = dict(row)

    preset = None
    preset_blocks = []
    if chat.get("preset_id"):
        async with db.execute("SELECT * FROM presets WHERE id = ?", (chat["preset_id"],)) as cur:
            row = await cur.fetchone()
            if row:
                preset = dict(row)
        if preset:
            async with db.execute(
                "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid",
                (preset["id"],)
            ) as cur:
                preset_blocks = [dict(r) for r in await cur.fetchall()]

    async with db.execute("SELECT * FROM providers") as cur:
        providers = [dict(r) for r in await cur.fetchall()]

    # ── Chats for right sidebar ───────────────────────────────────────────────
    chats_sidebar = []
    if chat.get("character_id"):
        async with db.execute(
            "SELECT * FROM chats WHERE character_id = ? ORDER BY updated_at DESC",
            (chat["character_id"],)
        ) as cur:
            chats_sidebar = [dict(r) for r in await cur.fetchall()]
    else:
        async with db.execute("SELECT * FROM chats ORDER BY updated_at DESC") as cur:
            chats_sidebar = [dict(r) for r in await cur.fetchall()]

    return templates.TemplateResponse(request, "chat.html", {
        "chat": chat,
        "chat_id": chat_id,
        "messages": messages,
        "character": char,
        "persona": persona,
        "preset": preset,
        "preset_blocks": preset_blocks,
        "providers": providers,
        "chats": chats_sidebar,
        "current_character_id": chat.get("character_id"),
        "current_persona_id": chat.get("persona_id"),
        "current_preset_id": preset["id"] if preset else None,
    })


@router.get("/characters", response_class=HTMLResponse)
async def characters_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM characters ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
        characters = []
        for r in rows:
            c = dict(r)
            try:
                c["card"] = json.loads(r["card_json"] or "{}")
            except Exception:
                c["card"] = {}
            async with db.execute(
                "SELECT * FROM char_blocks WHERE character_id = ? ORDER BY position, rowid",
                (r["id"],)
            ) as bcur:
                c["blocks"] = [dict(b) for b in await bcur.fetchall()]
            characters.append(c)

    return templates.TemplateResponse(request, "characters.html", {
        "characters": characters,
    })


@router.get("/presets", response_class=HTMLResponse)
async def presets_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM presets ORDER BY created_at DESC") as cur:
        presets = [dict(r) for r in await cur.fetchall()]
    for p in presets:
        async with db.execute(
            "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid",
            (p["id"],)
        ) as cur:
            p["blocks"] = [dict(r) for r in await cur.fetchall()]

    return templates.TemplateResponse(request, "presets.html", {
        "presets": presets,
    })


@router.get("/providers", response_class=HTMLResponse)
async def providers_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM providers ORDER BY created_at DESC") as cur:
        providers = [dict(r) for r in await cur.fetchall()]
    return templates.TemplateResponse(request, "providers.html", {
        "providers": providers,
    })


@router.get("/personas", response_class=HTMLResponse)
async def personas_page(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM personas ORDER BY created_at DESC") as cur:
        personas = [dict(r) for r in await cur.fetchall()]
    return templates.TemplateResponse(request, "personas.html", {
        "personas": personas,
    })


# ── Partials ────────────────────────────────────────────────────────────────

@router.get("/partials/message-list/{chat_id}", response_class=HTMLResponse)
async def message_list_partial(request: Request, chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("""
        SELECT m.id, m.role, m.position, m.active_index, mv.content, mv.variant_index,
               (SELECT COUNT(*) FROM message_variants WHERE message_id = m.id) as variant_count
        FROM messages m
        JOIN message_variants mv ON mv.message_id = m.id AND mv.variant_index = m.active_index
        WHERE m.chat_id = ?
        ORDER BY m.position
    """, (chat_id,)) as cur:
        messages = [dict(r) for r in await cur.fetchall()]

    char = None
    persona = None
    async with db.execute("SELECT * FROM chats WHERE id = ?", (chat_id,)) as cur:
        chat_row = await cur.fetchone()
    if chat_row:
        chat = dict(chat_row)
        if chat.get("character_id"):
            async with db.execute("SELECT * FROM characters WHERE id = ?", (chat["character_id"],)) as cur:
                row = await cur.fetchone()
                if row:
                    char = dict(row)
                    try:
                        char["card"] = json.loads(row["card_json"] or "{}")
                    except Exception:
                        char["card"] = {}
        if chat.get("persona_id"):
            async with db.execute("SELECT * FROM personas WHERE id = ?", (chat["persona_id"],)) as cur:
                row = await cur.fetchone()
                if row:
                    persona = dict(row)
        if not persona:
            async with db.execute("SELECT * FROM personas ORDER BY created_at LIMIT 1") as cur:
                row = await cur.fetchone()
                if row:
                    persona = dict(row)

    return templates.TemplateResponse(request, "message_list.html", {
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
    if character_id:
        async with db.execute(
            "SELECT * FROM chats WHERE character_id = ? ORDER BY updated_at DESC",
            (character_id,)
        ) as cur:
            chats = [dict(r) for r in await cur.fetchall()]
    else:
        async with db.execute("SELECT * FROM chats ORDER BY updated_at DESC") as cur:
            chats = [dict(r) for r in await cur.fetchall()]

    return templates.TemplateResponse(request, "chat_list.html", {
        "chats": chats,
        "current_chat_id": current_chat_id,
    })


@router.get("/partials/char-selector", response_class=HTMLResponse)
async def char_selector_partial(request: Request, chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM characters ORDER BY created_at DESC") as cur:
        characters = [dict(r) for r in await cur.fetchall()]
    current_character_id = None
    async with db.execute("SELECT character_id FROM chats WHERE id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
        if row:
            current_character_id = row["character_id"]
    return templates.TemplateResponse(request, "char_selector.html", {
        "characters": characters,
        "chat_id": chat_id,
        "current_character_id": current_character_id,
    })


@router.get("/partials/persona-selector", response_class=HTMLResponse)
async def persona_selector_partial(request: Request, chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM personas ORDER BY created_at DESC") as cur:
        personas = [dict(r) for r in await cur.fetchall()]
    current_persona_id = None
    async with db.execute("SELECT persona_id FROM chats WHERE id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
        if row:
            current_persona_id = row["persona_id"]
    return templates.TemplateResponse(request, "persona_selector.html", {
        "personas": personas,
        "chat_id": chat_id,
        "current_persona_id": current_persona_id,
    })


@router.get("/partials/preset-selector", response_class=HTMLResponse)
async def preset_selector_partial(request: Request, chat_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM presets ORDER BY created_at DESC") as cur:
        presets = [dict(r) for r in await cur.fetchall()]
    current_preset_id = None
    async with db.execute("SELECT preset_id FROM chats WHERE id = ?", (chat_id,)) as cur:
        row = await cur.fetchone()
        if row:
            current_preset_id = row["preset_id"]
    return templates.TemplateResponse(request, "preset_selector.html", {
        "presets": presets,
        "chat_id": chat_id,
        "current_preset_id": current_preset_id,
    })


@router.get("/partials/prompt-arranger/{preset_id}", response_class=HTMLResponse)
async def prompt_arranger_partial(request: Request, preset_id: str, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute(
        "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid",
        (preset_id,)
    ) as cur:
        blocks = [dict(r) for r in await cur.fetchall()]
    return templates.TemplateResponse(request, "prompt_arranger.html", {
        "blocks": blocks,
        "preset_id": preset_id,
    })


@router.get("/partials/sampler-modal", response_class=HTMLResponse)
async def sampler_modal_partial(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM providers") as cur:
        providers = [dict(r) for r in await cur.fetchall()]
    return templates.TemplateResponse(request, "sampler_modal.html", {
        "providers": providers,
    })

# ── Modal partials ───────────────────────────────────────────────────────────

@router.get("/partials/providers-modal", response_class=HTMLResponse)
async def providers_modal_partial(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM providers ORDER BY created_at DESC") as cur:
        providers = [dict(r) for r in await cur.fetchall()]
    return templates.TemplateResponse(request, "providers_modal.html", {
        "request": request,
        "providers": providers,
    })


@router.get("/partials/characters-modal", response_class=HTMLResponse)
async def characters_modal_partial(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM characters ORDER BY created_at DESC") as cur:
        rows = await cur.fetchall()
        characters = []
        for r in rows:
            c = dict(r)
            try:
                c["card"] = json.loads(r["card_json"] or "{}")
            except Exception:
                c["card"] = {}
            async with db.execute(
                "SELECT * FROM char_blocks WHERE character_id = ? ORDER BY position, rowid",
                (r["id"],)
            ) as bcur:
                c["blocks"] = [dict(b) for b in await bcur.fetchall()]
            characters.append(c)
    return templates.TemplateResponse(request, "characters_modal.html", {
        "request": request,
        "characters": characters,
    })


@router.get("/partials/presets-modal", response_class=HTMLResponse)
async def presets_modal_partial(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM presets ORDER BY created_at DESC") as cur:
        presets = [dict(r) for r in await cur.fetchall()]
    for p in presets:
        async with db.execute(
            "SELECT * FROM preset_blocks WHERE preset_id = ? ORDER BY position, rowid",
            (p["id"],)
        ) as cur:
            p["blocks"] = [dict(r) for r in await cur.fetchall()]
    return templates.TemplateResponse(request, "presets_modal.html", {
        "request": request,
        "presets": presets,
    })


@router.get("/partials/personas-modal", response_class=HTMLResponse)
async def personas_modal_partial(request: Request, db: aiosqlite.Connection = Depends(get_db)):
    async with db.execute("SELECT * FROM personas ORDER BY created_at DESC") as cur:
        personas = [dict(r) for r in await cur.fetchall()]
    return templates.TemplateResponse(request, "personas_modal.html", {
        "request": request,
        "personas": personas,
    })
