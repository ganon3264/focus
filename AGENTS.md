# Focus — Agent Quick Reference

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI (async) + aiosqlite (SQLite, WAL mode) |
| Templates | Jinja2 (server-side rendering) |
| Frontend | HTMX + Alpine.js (hypermedia SPA) |
| CSS | Tailwind CSS v4 (`tailwind-input.css` → `tailwind.css`) + custom `style.css` |
| Build / Pkg | `uv` + `hatchling` |
| Tests | `pytest with node runner` + `pytest-asyncio` → `uv run pytest tests/` (USER runs after changes) |
| Tailwind compile | `./bin/tailwindcss-linux-x64 -i static/tailwind-input.css -o static/tailwind.css --minify` (USER must run — agent env can't) |
| Start | `./start.sh` |

## Project structure

```
focus/                  # Python package
  database.py           # DB schema + init
  models.py             # Pydantic models
  crud.py               # DB read/update helpers
  routers/              # FastAPI route handlers
    pages.py            # Server-rendered HTML pages + HTMX partials
    chats.py, characters.py, presets.py, ...  # CRUD endpoints
    stream.py, stream_utils.py  # LLM streaming + prompt assembly
  providers/            # LLM provider implementations (OpenAI, Google, etc.)

templates/              # Full-page Jinja2 templates (base.html, chat.html, etc.)
partials/               # HTMX partial templates
  modal_shell.html      # Shared modal macro: modal_shell() + modal_footer()
  modals/               # Modal content partials
  presets/              # Preset-related partials (arranger, selector, etc.)
  chat/                 # Chat sidebar partials (char/persona lists)

static/
  style.css             # Design system: CSS vars (--surface, --border, --accent, --radius-*, --z-*, --modal-backdrop)
  tailwind-input.css    # Tailwind source (theme, @source paths, .hidden { display:none !important })
  js/                   # Custom JS modules
    state_manager.js    # Central state (character_id, persona_id, preset_id, provider_id, provider_type)
    api_paths.js        # API route builders (window.api)
    status_panel.js     # Bottom status bar
    chat_stream.js      # SSE streaming handler
  vendor/               # Third-party: htmx, alpine, marked, purify, sortable, cropper
```

## State management — THE critical pattern

**Single source of truth: `StateManager`** (`static/js/state_manager.js`)

Loads in `<head>`. Holds 5 fields:

| Field | Persistence | Event emitted |
|---|---|---|
| `character_id` | DB (PATCH /api/chats/{id}) | `character-changed` |
| `persona_id` | DB (PATCH /api/chats/{id}) | `persona-changed` |
| `preset_id` | DB (PATCH /api/chats/{id}) | `preset-changed` |
| `provider_id` | localStorage | `provider-changed` |
| `provider_type` | localStorage | `provider-changed` |

**How to use it:**

- **Set state:** `StateManager.setPreset(id)` / `setCharacter(id)` / `setPersona(id)` / `setProvider(id, type)`. Persistence to DB or localStorage is automatic.
- **Read state:** `StateManager.get('character_id')` or `StateManager.getAll()`.
- **React to changes:** `StateManager.on('preset-changed', function(e) { ... })`. Callbacks receive `{ prev, value }` (or `{ prevId, prevType, id, type }` for provider). Register them in `chat.html`.
- **Provider state** is session-scoped (localStorage). Chat-level fields (character/persona/preset) are chat-scoped (DB via PATCH /api/chats/{id}).
- Existing callbacks in `chat.html` already handle: reloading `#preset-variables`, reloading `#arranger-modal-body` on preset change, and reloading the arranger on character/persona change. Add new reactions there — don't inline them in `@click` handlers.

## Modals

**Shared shell:** `partials/modal_shell.html`

```jinja2
{% from "modal_shell.html" import modal_shell %}
{% call modal_shell('modal-id', 'Title') %}
  Body content here
{% endcall %}
```

Parameters: `id`, `title`, `max_width` (default 600px), `width` (default 95vw), `content_style`, `z_index`, `role`, `close_fn`, `overlay_close`, `overlay_class`.

A `modal_footer()` macro exists for standardized action buttons:
```jinja2
{% call modal_footer() %}
  <button class="btn btn-secondary" onclick="closeModal('id')">Cancel</button>
  <button class="btn btn-primary">Save</button>
{% endcall %}
```

**CSS classes:** `.modal-overlay` (uses `var(--z-modal)` by default), `.modal-overlay.heavy` (for lightbox/crop — uses `var(--modal-backdrop-heavy)`), `.modal-content`, `.modal-header`, `.modal-title`, `.modal-footer`.

**Z-index scale** (defined in `style.css :root`):
- `--z-modal: 50` — base modals
- `--z-modal-sub: 100` — sub-modals (provider create, edit message)
- `--z-modal-high: 1000` — editor modals (block edit, var edit, text expander, rename)
- `--z-overlay: 10000` — full-screen overlays (lightbox, crop, trash)
- `--z-max: 10010` — confirm dialogs (must always be on top)

**TO SHOW/HIDE:** Always use `classList.remove('hidden')` / `add('hidden')`, never `style.display`. The `hidden` class has `display:none !important` in `tailwind-input.css`.

**openModal/closeModal** are defined in `chat.html`. They handle lazy-loading for characters/personas/providers modals.

## CSS design system

All colors and measurements use CSS custom properties defined in `style.css :root`:

```
--bg, --surface, --surface-2, --surface-3    # background hierarchy
--border, --border-hover                     # border colors
--text, --text-muted, --text-faint           # text colors
--accent, --accent-hover, --accent-dim       # accent (indigo)
--danger, --danger-hover, --danger-dim       # danger (red)
--radius-sm: 6px, --radius-md: 10px, --radius-lg: 14px, --radius-xl: 20px
--shadow-sm, --shadow-md, --shadow-lg, --shadow-glow
--transition: 0.2s cubic-bezier(0.16, 1, 0.3, 1)
```

Button classes: `.btn` base, `.btn-primary` (accent), `.btn-secondary` (surface-2), `.btn-danger` (red), `.btn-sm` (small).

Form classes: `.form-group`, `.form-control` (inputs/textareas/selects). Extends native elements via `:where()`.

Always prefer CSS variables over hardcoded colors/radii in inline styles.

## HTMX + Alpine patterns

- **Server-rendered page loads** → Jinja2 templates with server state
- **Partial updates** → `htmx.ajax('GET', url, {target, swap})`
- **Client interactivity** → Alpine.js `x-data`, `x-show`, `@click`, `x-model`
- **When updating a section via HTMX that contains Alpine components**, be aware that alpine:init runs again for the new markup
- The preset selector uses Alpine `x-data` + `@click` handlers. The `@click` handler updates Alpine local state (`selectedId`, `selectedName`) THEN calls `StateManager.setPreset(id)`. The StateManager callbacks handle everything else (variables, arranger).

## Handling provider state

- `setActiveProvider(id, name, type)` in `modal_providers.js` calls `StateManager.setProvider(id, type)`
- StateManager writes to localStorage AND dispatches `provider-changed` (both callback + window CustomEvent for Alpine)
- Alpine components listen via `@provider-changed.window`
- JS modules listen via `StateManager.on('provider-changed', fn)` or `window.addEventListener('provider-changed', fn)`

## Tests

```
uv run pytest tests/ -x -q
```

Tests use isolated in-memory SQLite databases. Frontend tests use `httpx.ASGITransport` for full-stack async HTTP testing.

## Common gotchas

1. **Don't reload the preset selector via HTMX outerHTML swap** after state changes. It races with the DB PATCH. The `@click` handlers update Alpine state synchronously; the PATCH fires async for persistence only. Delete operations should click the fallback item (which calls `StateManager.setPreset`) then remove the deleted DOM node.

2. **`reloadPromptArranger` must always be defined** (unconditionally in chat.html). If it's inside `{% if preset %}`, it won't exist when the page loads with no preset selected, breaking the preset selector dropdown.

3. **`createEditModalHandlers`** (base.html) uses `cfg.stateKey` to find the current entity from StateManager. When reloading modal bodies after edits, always pass `?current_${stateKey}=...` so the active card highlight doesn't vanish.

4. **When adding new modals**, use the `modal_shell` macro. Don't duplicate the overlay/content/header structure. Use the z-index scale vars.

5. **When the arranger is reloaded via HTMX**, the `prompt_arranger.html` script block re-runs. It has a `!_arrangerScriptsLoaded` guard for one-time init (function definitions) + unconditional Sortable init per preset.

6. **Path references:** Jinja `{% include %}` paths are relative to templates/partials dirs. Static files are served from `/static/`. API endpoints are in `window.api` (see `api_paths.js`).

## File naming conventions

- Templates: `snake_case.html`
- Python modules: `snake_case.py`
- JS modules: `snake_case.js`
- CSS: `style.css`, `tailwind-input.css`, `tailwind.css`
- Partials: nested under `partials/<feature>/`
- Modals: `partials/modals/<name>_modal.html`
