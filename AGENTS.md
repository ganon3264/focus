# Focus — Agent Quick Reference

## Stack

| Layer | Tech |
|---|---|
| Backend | FastAPI (async) + aiosqlite (SQLite, WAL mode) |
| Templates | Jinja2 (server-side rendering) |
| Frontend | HTMX 2.x + Alpine.js 3.x (hypermedia SPA) |
| CSS | Tailwind CSS v4 (`tailwind-input.css` → `tailwind.css`) + custom `style.css` |
| Build / Pkg | `uv` + `hatchling` |
| Tests | `pytest` + `pytest-asyncio` + Node.js for JS tests → `uv run pytest tests/ -v` |
| Tailwind compile | `./bin/tailwindcss-linux-x64 -i static/tailwind-input.css -o static/tailwind.css --minify` (USER must run — agent env can't) |
| Vendor sync | `./vendor-sync.py` — downloads all third-party JS/CSS from CDN (no npm) |
| Start | `./start.sh` (vendor-sync → tailwind → uv run main.py) |
| Test runner | `./test.sh` — runs `uv run pytest tests/ -v` |

## Project structure

```
focus/
  __init__.py               # Package init
  main.py                   # FastAPI app creation, lifespan, middleware, router includes
  crud.py                   # DB read/update helpers (dynamic_update, upload_block_image, load_entity_blocks, get_*)
  prompt_chain.py           # Prompt assembly engine (assemble_prompt, partition_blocks, resolve_variable_blocks)
  exchange.py               # Import/export engine (.focus archive format, ZIP with manifest + database.json + assets)
  backup.py                 # Backup management (create/list/restore/delete .focus snapshots in data/backups/)
  core/
    __init__.py
    database.py             # DB schema (13 tables), migrations (v0.2–v0.5), seed data, init_db()
    models.py               # Pydantic models (ProviderCreate/Out, CharBlock*, CharacterCreate/Update, PresetBlock*, ChatCreate, StreamRequest, ItemizerRequest, SettingsUpdate, ActiveProviderUpdate, ExportRequest, enums)
    paths.py                # Filesystem paths (configurable via FOCUS_DATA_DIR, FOCUS_BACKUPS_DIR env vars)
    utils.py                # TTLCache (async-safe), MIME maps, image/audio token estimation, now_iso(), resolve_secret_key(), variable_group_name()
    logger.py               # Colored console logging, FOCUS_DEBUG env var, get_logger() helper
    macros.py               # Template macro engine (build_base_macros, apply_macros, extract_setvars)
    card_parser.py          # PNG character card parser (v1/v2 spec, chara chunk extraction)
    message_render.py       # Server-side message segmentation: render_message_segments() splits content into text/reasoning/tool_boundary typed segments for Jinja2 rendering
  providers/
    __init__.py             # create_provider(row) factory — dispatches by row["type"]
    base.py                 # Abstract BaseProvider — __init__, _build_headers(), fetch_models(), abstract stream_complete()
    google_base.py          # Shared Google provider logic — builds genai Content/Part from messages, handles thoughts/reasoning, streaming via genai SDK
    openai_compat.py        # OpenAI-compatible API provider. Handles reasoning models (o1/o3), wraps reasoning in <think> tags. Default base URL: http://localhost:8080/v1
    openrouter.py           # OpenRouter provider (subclass of openai_compat). Adds or_route, or_quant, or_no_fallbacks, reasoning config via extra_body
    deepseek.py             # DeepSeek provider (subclass of openai_compat). Adds deepseek thinking toggle via extra_body
    moonshot.py             # Moonshot/Kimi provider (subclass of openai_compat). Adds Kimi thinking param via extra_body
    google_aistudio.py      # Google AI Studio provider (subclass of GoogleProviderBase). All safety filters OFF. Uses genai.Client()
    google_vertex.py        # Google Vertex AI provider (subclass of GoogleProviderBase). Supports service account JSON or ADC. Requires project+region
  routers/
    __init__.py             # Imports all routers
    pages.py                # Server-rendered HTML pages + HTMX partials (mounted at root)
    chats.py                # /api/chats — CRUD, messages, variants, swipe, branch, attachments, bulk delete
    characters.py           # /api/characters — CRUD, PNG import, soft-delete/trash/restore, blocks+media, images
    presets.py              # /api/presets — CRUD, import (SillyTavern JSON), blocks (reorder, add, update with mutual-exclusivity), images
    providers.py            # /api/providers — CRUD, fetch_models (5-min TTL cache), OpenRouter models/endpoints, secrets sub-system, balance (1-min TTL cache per key)
    personas.py             # /api/personas — CRUD, avatar upload, images, "User" persona protected from delete
    stream.py               # /api/stream — streaming completion (SSE), prompt context, multimodal, Claude caching, OpenRouter modality; /api/itemize — token counting
    stream_utils.py         # Shared utilities: get_prompt_context, _get_history, filter_unsupported_modalities, apply_claude_caching
    exchange.py             # /api/export — export entities as .focus ZIP; /api/import — import .focus ZIP
    backup.py               # /api/backups — create/list/restore/delete backups
    settings.py             # /api/settings — key/value store, active provider, DB-persisted sampler configs

templates/                  # Full-page Jinja2 templates
  base.html                 # Root layout: head (theme+CSS+vendor JS), SVG sprite, inline utilities (expandGet, reloadPromptArranger, buildMediaThumbnail, setupDropZone, createEditModalHandlers), global overlays (confirm/lightbox/crop modals), script includes
  chat.html                 # Main chat page: 3-panel layout, all modal definitions (~12), StateManager init + callbacks, variable management scripts (_varScriptsLoaded)
  characters.html           # Character card editor: Alpine charEditor component, block CRUD, greeting management, PNG import, media grid
  personas.html             # Persona CRUD page: card grid, avatar upload, delete confirmation
  presets.html              # Preset management page: sidebar list, HTMX-loaded preset editor
  providers.html            # Provider CRUD page: card grid with hx-delete, add form
  macros.html               # Shared macro library: _js_str, custom_select (Alpine dropdown), SVG icon macros, media_thumbnail

partials/                   # HTMX partial templates
  modal_shell.html          # Shared modal macro: modal_shell() + modal_footer() — defines overlay/content/header/footer structure
  chat/
    message_list.html        # Message list wrapper with hidden data div, iteration over messages, #scroll-sentinel
    message.html             # Single message: avatar, name, model, toolbar (swipe/regen/branch/edit/delete), attachments, segment-based content (text/reasoning/tool-calls with inline rendering), delete checkbox
    char_selector.html       # Character list for left sidebar — HTMX click filters chat list
    persona_selector.html    # Persona list for sidebar — click calls StateManager.setPersona()
    chat_list.html           # Chat list for right sidebar — links to /chat/{id}, delete with customConfirm
  personas/
    persona_card.html        # Persona card component: avatar, name, description, avatar upload, delete
  modals/
    confirm_modal.html       # Global confirm dialog (z-index 10010, role=alertdialog). Exposes customConfirm(msg, cb), intercepts htmx:confirm events
    sampler_modal.html       # Generation parameters modal (3 tabs: Standard/Advanced/Custom). Alpine component with provider-specific visibility, localStorage persistence, exposes getActiveSamplers()
    itemizer_modal.html      # Prompt itemizer — POSTs to /api/itemize, displays tokenized prompt by role. Listens for @itemizer-open.window
    character_modal_card.html  # Character card partial for modal grid (compact/full views, edit/delete)
    characters_modal.html    # Character selection modal: search, sort, compact/grid view, import PNG, trash bin with restore, ListManager.setup()
    persona_modal_card.html  # Persona card partial for modal grid (compact/full views, edit/delete)
    personas_modal.html      # Persona selection modal: search, sort, compact view, delete (User protected), ListManager.setup()
    providers_modal.html     # Provider selection & management: cards, inline edit, secrets sub-modal, fetch-models sub-modal, OpenRouter-specific fields
    provider_create_modal.html  # Create provider form: name, type, base_url, API key (with secrets), model (with fetch), OpenRouter/Vertex-specific fields
    edit_entity_modal.html   # Reusable entity edit modal (characters + personas): avatar with crop, name, description, media grid. Parameterized via prefix/modal_id/entity_name/upload_fn/avatar_fn/submit_fn
    edit_message_modal.html  # Edit message modal (z-index 100): hidden thought textarea, content textarea, attachment management with add/upload/delete
    text_expander.html       # Full-height monospace textarea for long fields (z-index 1000). Exposes openTextExpander/closeTextExpander/saveTextExpander
    theme_modal.html         # Theme customizer: 3 preset themes (Slate/Midnight OLED/Light), per-variable color pickers, live preview, save
    backup_modal.html        # Backups/export modal: create/restore/delete backups, export with granular entity selection, import .focus files, database cleanup
    export_entities.html     # Entity selection list for export modal — renders checklist of entities with images
  presets/
    sidebar_item.html        # Sidebar preset list item — click loads preset editor, delete button
    preset_selector.html     # Alpine-powered preset dropdown: select (StateManager.setPreset), new (HTMX POST + reload), import (file input), rename (inline modal at z-index 1000), delete (fallback click pattern)
    preset_variables.html    # Variable groups: sortable groups and options, expandable via expandGet/expandToggle, option toggle/edit/delete, Add Variable button
    prompt_arranger.html     # Drag-and-drop prompt arranger (Sortable.js): add block dropdown, block list, inline block-edit-modal (z-index 1000), Script with _arrangerScriptsLoaded guard
    prompt_block.html        # Individual arranger block: drag handle, expand/collapse, name, enable toggle, delete, role selector, content preview, injection controls, media attachments
    presets_modal.html       # Preset management within a modal: sidebar list + HTMX-loaded editor
    preset_editor.html       # Thin wrapper including preset_variables.html + prompt_arranger.html

static/
  chat_stream.js            # Core SSE streaming engine: triggerGeneration, AbortController, branchFromMessage, send/regen mode, file upload before generation, updateSendButtonState, resizeTextarea, DOMContentLoaded/afterSwap init (static/js/core/chat_stream.js)
  reasoning_utils.js         # Reasoning toggle visibility, syncReasoningButtons, preserveOpenStates, toggleReasoningBlock (static/js/messages/reasoning_utils.js)
  message_refresh.js         # Message DOM refresh: _refreshMessageNodes (internal strategy selector), refreshMessagesAfterStream, refreshSingleMessage, _refreshChatList, _replaceMessageNode (static/js/messages/message_refresh.js)
  favicon.svg               # SVG favicon (lightning bolt)
  style.css                 # Design system: CSS vars, @layer base/components/utilities — all visual classes
  tailwind-input.css        # Tailwind source: @source paths (templates/partials/static), @theme tokens, .hidden { display:none !important }
  tailwind.css              # Compiled Tailwind output (gitignored)
  js/
    state_manager.js        # Central state: character_id, persona_id, preset_id, provider_id, provider_type. set/get/on/off + dispatchEvent for Alpine
    api_paths.js            # API route builders (window.api) — all endpoint paths as functions/properties
    status_panel.js         # Bottom status bar: provider/preset/model display, Claude cache countdown timer, newChat()
    scroll_manager.js       # Auto-scroll via IntersectionObserver, scroll sentinel, RAF-based scrollToBottom
    message_renderer.js     # Client-side message rendering: escapeHtml, extractThoughtsSafely, renderMessage (marked + DOMPurify + code copy buttons + accent-quote + reasoning block generation)
    msg_dom.js              # DOM builders: createUserMessageDiv (with attachment previews), createAssistantPlaceholderDiv (with reasoning toggle)
    chat_stream.js          # Core streaming engine — see core/chat_stream.js
    file_staging.js         # File staging area: drag/paste/upload pipeline, image crop before send, preview rendering
    delete_mode.js          # Multi-select bulk delete mode: toolbar toggle, auto-select range, bulkDeleteSelected
    edit_message.js         # Message edit modal: load message, split thought/body, render attachments, save/upload/delete
    message_pruner.js       # DOM virtualization: replaces off-screen message nodes with height placeholders, restores on scroll, RAF-throttled
    lightbox.js             # Image lightbox + Cropper.js crop modal: openLightbox, openCropModal, handleAvatarUpload
    list_manager.js         # Config-driven grid manager: filter, sort (az/za/newest/oldest), compact/full view toggle, newItem creation. Used by characters/personas modals
    backup_manager.js       # Backup/export/import UI: BackupManager singleton, create/restore/delete backups, granular export (entities+chats+providers+secrets), .focus import, database cleanup
    char_editor.js          # Character card editor: Alpine charEditor component, block CRUD, greeting management, media upload per block, PNG import
    modal_providers.js      # Provider CRUD: setActiveProvider, save/submit, OpenRouter model/route/quant fetching, secrets management, renderMacroSelect Alpine dropdown generator, extractData form normalizer
    modal_char_edit.js      # Wiring: calls createEditModalHandlers with character-specific config
    modal_persona_edit.js   # Wiring: calls createEditModalHandlers with persona-specific config
    theme_manager.js        # Theme engine: 3 presets (default/midnight/light), CSS var manipulation, live preview, localStorage persistence
  vendor/
    htmx2.min.js            # HTMX 2.x — hypermedia AJAX
    alpine.min.js           # Alpine.js 3.x — reactive UI
    alpine-collapse.min.js  # Alpine Collapse plugin — x-collapse transitions
    marked.umd.js           # marked — markdown-to-HTML
    purify.min.js           # DOMPurify — XSS sanitization
    sortable.min.js         # SortableJS — drag-and-drop
    cropper.min.js          # Cropper.js 2.x — image cropping
    inter.css               # Inter font @font-face declarations
    fonts/                  # Inter font files (woff2)
```

## State management — THE critical pattern

**Single source of truth: `StateManager`** (`static/js/core/state_manager.js`)

Loads in `<head>`. Holds 5 fields:

| Field | Persistence | Event emitted |
|---|---|---|
| `character_id` | DB (PATCH /api/chats/{id}) | `character-changed` |
| `persona_id` | DB (PATCH /api/chats/{id}) | `persona-changed` |
| `preset_id` | DB (PATCH /api/chats/{id}) | `preset-changed` |
| `provider_id` | localStorage + DB (`/api/settings/active-provider`) | `provider-changed` |
| `provider_type` | localStorage + DB (`/api/settings/active-provider`) | `provider-changed` |

**How to use it:**

- **Set state:** `StateManager.setPreset(id)` / `setCharacter(id)` / `setPersona(id)` / `setProvider(id, type)`. Persistence to DB or localStorage is automatic.
- **Read state:** `StateManager.get('character_id')` or `StateManager.getAll()`.
- **React to changes:** `StateManager.on('preset-changed', function(e) { ... })`. Callbacks receive `{ prev, value }` (or `{ prevId, prevType, id, type }` for provider). Register them in `chat.html`.
- **Alpine reacts too:** `setPreset` and `setProvider` also dispatch a matching `window.CustomEvent` (e.g. `@preset-changed.window` / `@provider-changed.window`). `setCharacter` and `setPersona` emit listener-only events; Alpine components listening to those must use the `StateManager.on(...)` callback registered in `chat.html`, not `@character-changed.window`.
- **Provider state** is dual-persisted: localStorage (session) + DB via `/api/settings/active-provider`. Chat-level fields (character/persona/preset) are chat-scoped (DB via PATCH /api/chats/{id}).
- Existing callbacks in `chat.html` already handle: reloading `#preset-variables`, reloading `#arranger-modal-body` on preset change, reloading arranger and sampler on character/persona change. Add new reactions there — don't inline them in `@click` handlers.

**Important:** `setPreset(null)` clears the preset. `setCharacter(null)` / `setPersona(null)` are also valid. The PATCH body shape is `{field_name: value}` (value can be null).

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

**All modal types:**

| Modal ID | File | Z-index | Purpose |
|---|---|---|---|
| `global-confirm-modal` | `modals/confirm_modal.html` | 10010 | alertdialog — confirm actions, intercepts htmx:confirm |
| `modal-sampler` | `modals/sampler_modal.html` | 50 | Generation parameters (3 tabs, provider-specific) |
| `modal-itemizer` | `modals/itemizer_modal.html` | 50 | Prompt token count viewer |
| `modal-characters` | `modals/characters_modal.html` | 50 | Character selection with search/sort/trash |
| `modal-personas` | `modals/personas_modal.html` | 50 | Persona selection with search/sort |
| `modal-providers` | `modals/providers_modal.html` | 50 | Provider selection & management |
| `modal-provider-create` | `modals/provider_create_modal.html` | 100 | Create provider form |
| `modal-edit-character` | `modals/edit_entity_modal.html` | 100 | Edit character card (reused with different params) |
| `modal-edit-persona` | `modals/edit_entity_modal.html` | 100 | Edit persona card (reused with different params) |
| `modal-edit-message` | `modals/edit_message_modal.html` | 100 | Edit message with attachment management |
| `modal-text-expander` | `modals/text_expander.html` | 1000 | Full-height monospace textarea for long fields |
| `block-edit-modal` | `presets/prompt_arranger.html` (inline) | 1000 | Edit arranger block content |
| `var-edit-modal` | `chat.html` (inline) | 1000 | Edit variable option |
| `modal-themes` | `modals/theme_modal.html` | 100 | Theme customizer with color pickers |
| `modal-backups` | `modals/backup_modal.html` | 50 | Backup/restore/export/import |
| `modal-export` | `modals/backup_modal.html` (inline) | 100 | Granular entity export selection |
| `modal-entity-select` | `modals/backup_modal.html` (inline) | 200 | Entity checklist for export |
| `modal-fetch-models` | `modals/providers_modal.html` (inline) | 100 | Fetch and select models from provider |
| `modal-secrets` | `modals/providers_modal.html` (inline) | 100 | Secrets management (API keys) |
| Preset rename | `presets/preset_selector.html` (inline) | 1000 | Inline rename modal |
| `modal-arranger` | `chat.html` (inline) | 50 | Prompt arranger (drag-and-drop block list) |
| `lightbox` | `base.html` (inline) | 10000 | Image lightbox overlay |
| `crop-modal` | `base.html` (inline) | 10000 | Cropper.js avatar/image crop |
| `trash-modal` | `modals/characters_modal.html` (dynamic) | 10000 | Trash bin for soft-deleted characters |
| `persona-trash-modal` | `modals/personas_modal.html` (dynamic) | 10000 | Trash bin for soft-deleted personas |
| `chat-trash-modal` | `chat/chat_list.html` (dynamic) | 10000 | Trash bin for soft-deleted chats |

**Z-index scale** (defined in `style.css :root`):
- `--z-modal: 50` — base modals
- `--z-modal-sub: 100` — sub-modals (provider create, edit message, entity edit)
- `--z-modal-high: 1000` — editor modals (block edit, var edit, text expander, rename)
- `--z-overlay: 10000` — full-screen overlays (lightbox, crop, trash)
- `--z-max: 10010` — confirm dialogs (must always be on top)

**CSS classes:** `.modal-overlay` (uses `var(--z-modal)` by default), `.modal-overlay.heavy` (for lightbox/crop — uses `var(--modal-backdrop-heavy)`), `.modal-content`, `.modal-header`, `.modal-title`, `.modal-footer`.

**TO SHOW/HIDE:** Always use `classList.remove('hidden')` / `add('hidden')`, never `style.display`. The `hidden` class has `display:none !important` in `tailwind-input.css`.

**openModal/closeModal** are defined in `chat.html`. They handle body fetching for characters/personas/providers modals via `htmx.ajax`.

**Important:** The `edit_entity_modal.html` is reused for both characters and personas via Jinja variables (`prefix`, `modal_id`, `entity_name`, etc.). The `backup_modal.html` defines 3 modals in one file. The arranger, provider, and preset selector define sub-modals inline rather than in separate files.

## CSS design system

All colors and measurements use CSS custom properties defined in `style.css :root`:

```
--bg, --surface, --surface-2, --surface-3    # background hierarchy
--border, --border-hover                     # border colors
--text, --text-muted, --text-faint           # text colors
--accent, --accent-hover, --accent-dim, --accent-faint  # accent (indigo) with derivatives
--danger, --danger-hover, --danger-dim       # danger (red)
--active-bg, --active-border, --active-text  # active state system (uses color-mix())
--text-on-accent                             # white text on accent backgrounds
--radius-sm: 6px, --radius-md: 10px, --radius-lg: 14px, --radius-xl: 20px, --radius-full: 9999px
--shadow-sm, --shadow-md, --shadow-lg, --shadow-glow
--transition: 0.2s cubic-bezier(0.16, 1, 0.3, 1)
--font-sans: 'Inter', system-ui, sans-serif
--modal-backdrop, --modal-backdrop-heavy
--z-* scale (see modals section)
```

Button classes: `.btn` base, `.btn-primary` (accent), `.btn-secondary` (surface-2), `.btn-danger` (red), `.btn-sm` (small).

Form classes: `.form-group`, `.form-control` (inputs/textareas/selects).

Always prefer CSS variables over hardcoded colors/radii in inline styles.

**Active state system:** Use `--active-bg`, `--active-border`, `--active-text` (all built via `color-mix()` from `--accent`) for sidebar items, cards, tabs, and arranger items. Don't hardcode active colors.

**Key CSS patterns:**
- Glassmorphic input bar via `backdrop-filter: blur(16px)` + `color-mix()`
- Hover-reveal toolbars (`.message:hover .toolbar`)
- Code copy buttons (`.copy-btn` absolutely positioned in `<pre>`)
- Reasoning blocks (`.reasoning-block` + `.reasoning-summary` button + `.reasoning-content` — first block uses message-level toggle, subsequent blocks have individual `.reasoning-summary` buttons)
- Tool call sections (`.tool-calls-section` with `.details.tool-call` — collapsed by default, rendered inline between text segments)
- Markdown processing gate (`.markdown-content:not(.processed)` hidden until marked.js renders)
- Auto-grow grid (`.grid` with `repeat(auto-fill, minmax(180px, 1fr))`)

## HTMX + Alpine patterns

- **Server-rendered page loads** → Jinja2 templates with server state
- **Partial updates** → `htmx.ajax('GET', url, {target, swap})`
- **Client interactivity** → Alpine.js `x-data`, `x-show`, `@click`, `x-model`
- **When updating a section via HTMX that contains Alpine components**, be aware that `alpine:init` runs again for the new markup
- **Alpine components registered via `Alpine.data()`:** `samplerModal`, `itemizerModal`, `charEditor` — register in `alpine:init` event listener
- **Inline Alpine components** use object literals in `x-data` (dropdowns, expand/collapse, search/filter)
- **`expandGet`/`expandToggle`** — Set-based expand/collapse tracking that survives HTMX re-renders (unlike Alpine `x-data` which resets). Used by arranger blocks and variable groups.
- **`htmx:confirm` interception** — `confirm_modal.html` intercepts HTMX's `hx-confirm` attribute events and shows the custom `customConfirm()` modal instead of `window.confirm()`
- **Custom dropdowns** via `custom_select` macro (`macros.html`) — generates Alpine `x-data` with `@click.away`, `x-transition`, and z-index management via `x-effect`
- **HTMX + Alpine coordination** — StateManager dispatches `window.CustomEvent`; Alpine components listen via `@preset-changed.window` / `@provider-changed.window`
- **HTMX for partial content** — message list, chat list, preset variables, prompt arranger, modal bodies all loaded via `htmx.ajax`

## Data-action event dispatch system

**Central dispatcher:** `static/js/core/actions.js`

All `data-action` attributes on elements are handled by 4 delegated event listeners on `document`:

| Listener | Fires when | Form guard? |
|---|---|---|
| `click` | Any click on a `[data-action]` element or its descendants | ✅ Skips `<form>` |
| `submit` | Form submission | ❌ No guard (only correct path for form actions) |
| `change` | Change event (blur for text inputs, immediate for selects/checkboxes) | ✅ Skips `<form>` |
| `input` | Every keystroke (real-time) | ✅ Skips `<form>` |

**Form guard rule:** Every listener except `submit` has `if (el.tagName === 'FORM') return;`. This prevents arbitrary clicks/keystrokes inside a `<form data-action="...">` from triggering the form's action handler. Form actions only fire on actual `submit` events (clicking a submit button, pressing Enter in an input).

**Resolution:** `_resolveAction(name)` looks up the function on `window`:
- Simple names: `window[name]` (e.g. `data-action="deleteBlockMedia"` → `window.deleteBlockMedia`)
- Dotted names: traverses `window` object path (e.g. `data-action="BackupManager.doExport"` → `window.BackupManager.doExport`)

**Shared helper:** `window.resolveFormFromEvent(e)` (`actions.js:23`) — safely extracts the `<form>` element from any event, handling both click events (where `e.target` may be a child button) and submit events (where `e.target` IS the form):
```javascript
window.resolveFormFromEvent = function (e) {
  return e.target.tagName === 'FORM' ? e.target : (e.target.form || e.target.closest('form'));
};
```

**Requirements for `data-action` functions:**
- The function MUST be accessible on `window` (either assigned directly: `window.fn = function...`, or a plain declaration inside an IIFE that doesn't scope it locally).
- The function receives `(el, e)` where `el` is the element with `data-action` (found via `closest()`) and `e` is the raw event.
- For action wrappers that bridge to internal functions, see the `/* ── Action wrappers ── */` section in `actions.js`.

## Handling provider state

- `setActiveProvider(id, name, type)` in `modal_providers.js` calls `StateManager.setProvider(id, type)`
- StateManager writes to localStorage AND dispatches `provider-changed` (both callback + window CustomEvent for Alpine)
- Alpine components listen via `@provider-changed.window`
- JS modules listen via `StateManager.on('provider-changed', fn)` or `window.addEventListener('provider-changed', fn)`
- `modal_providers.js` dispatches custom events for async operations: `models-loading`, `models-loaded`, `models-error`, `secrets-loaded`
- Alpine components in `providers_modal.html` listen: `@models-loaded.window`, `@models-loading.window`, `@models-error.window`, `@secrets-loaded.window`
- **Balance fetch** (`get_provider_balance`) is cached backend-side via `_balance_cache` (1-min TTL) keyed on `type + hash(api_key)`. Providers sharing the same API key will share the cached balance. Frontend fetches per-provider and relies on the backend cache for dedup.

## Prompt chain & macros

**Prompt assembly** (`focus/prompt_chain.py`):

- `assemble_prompt()` — main entry point: sorts preset blocks → resolves variables → processes sentinel block types (char_description, char_personality, user_persona, char_blocks, chat_history) → injects in-chat blocks at specified depth → merges consecutive same-role messages → applies macros → handles `<think>`/`<thought_signature>`
- `partition_blocks()` — splits preset blocks into variable blocks vs regular blocks
- `resolve_variable_blocks()` — resolves macro chains among variable blocks (multi-pass until stable)
- `_build_content()` — constructs plain text or multimodal content arrays (text + images/audio)
- `_load_media()` — reads/compresses images/audio from disk into base64 data URLs
- `_merge_consecutive()` — merges adjacent same-role messages into one

**Template macros** (`focus/core/macros.py`):

- `build_base_macros(card, personaName, personaDesc)` — creates dict: `{{char}}`, `{{user}}`, `{{persona}}`, `{{description}}`, `{{personality}}`, `{{scenario}}`, `{{mes_example}}`, `{{time}}`, `{{date}}`, `{{weekday}}`, `{{time_of_day}}`
- `apply_macros(text, macros, max_passes=10)` — resolves `{{key}}`, `{{getvar::key}}`, `{{setvar::k::v}}`, `{{var::k::v}}`, `{{trim}}` (blank-line collapse). Multi-pass chain resolution (up to 10 passes, prevents infinite loops)
- `extract_setvars(text)` — extracts `{{setvar::k::v}}` / `{{var::k::v}}` declarations from content
- `build_base_macros` auto-classifies time of day (morning/afternoon/evening/night)

**Block types** (in `preset_blocks.block_type`):
- `text` — user-written content
- `char_description`, `char_personality`, `user_persona`, `char_blocks` — sentinel placeholders auto-populated from character/persona data
- `chat_history` — conversation history injected at position
- `variable` — multi-option groups resolved via `{{getvar::name}}`

**Injection depth/order:** Blocks with `injection_depth` set are injected into the conversation history at that depth (0 = most recent) and sorted by `injection_order` within the same depth.

## Backup & export system

**Backup manager** (`static/js/features/backup_manager.js`):
- `window.BackupManager` singleton with: `create()`, `restore(id)`, `delete(id)`, `loadList()`, `importFile(input)`, `openExportModal()`, `doExport()`, `cleanDatabase()`
- Backup files are `.focus` ZIP archives stored in `data/backups/` with timestamped filenames

**Export system** (`focus/exchange.py`):
- Export resolves cascading dependencies (chat → character → char_blocks → block_images), collects file paths, builds ZIP with `manifest.json` + `database.json` + asset files
- Granular selection: export specific entities by ID, or `["*"]` for all
- Optional include: providers, secrets, chats

**Import system** (`focus/exchange.py`):
- Validates archive structure, remaps all UUIDs to new IDs, rewrites foreign keys, renames colliding providers, writes assets to disk, inserts in dependency order
- Full round-trip safe: importing an export of everything creates a complete duplicate with new IDs

**Database cleanup** (`/api/db/clean`):
- Deletes soft-deleted chats and characters (is_deleted=1)
- Removes orphaned block_images and attachments
- Runs VACUUM

## Character card editor

**Full-page editor** at `/characters` (`templates/characters.html`):
- Alpine `charEditor` component (`static/js/features/char_editor.js`) with URL-based character navigation via `URLSearchParams`
- PNG card import (extracts `chara` chunk from PNG tEXt/iTXt metadata, v1/v2 spec)
- Character fields: name, description, personality, scenario, first message, mes_example, alternate greetings
- Advanced fields toggle with `x-collapse`
- Custom logic blocks: name, role (system/user/assistant), content, per-block media uploads
- Block/greeting CRUD via clone-template pattern
- Avatar upload with crop pipeline

## Sampler modal

**Generation parameters** (`partials/modals/sampler_modal.html`):
- 3 tabs: Standard (temperature, top_p, top_k, repetition_penalty, min_p), Advanced (mirostat, typical_p, etc.), Custom (raw JSON fields)
- Provider-specific parameter visibility (OpenRouter, OpenAI, DeepSeek, Moonshot, Google)
- Streaming/multimodal/reasoning toggles with effort levels
- Prompt caching controls (Claude)
- **Persistence:** localStorage key `sampler_${preset_id}_${provider_id}` + DB via `/api/settings` (flat key/value store with composite keys like `global_sampler_config_{providerId}`)
- **Integration:** exposes `window.getActiveSamplers()` for streaming code; listens to `@provider-changed.window` and `@preset-changed.window` for automatic reload

## Theme system

**Theme manager** (`static/js/ui/theme_manager.js`):
- 3 presets: **Slate** (dark indigo, default), **Midnight OLED** (true black + blue), **Light** (white + indigo)
- Each preset defines: `--bg`, `--surface`, `--surface-2`, `--surface-3`, `--border`, `--accent`, `--text`, `--text-muted`
- Live preview via `element.style.setProperty()` on `:root`
- Persistence: localStorage key `focus-custom-theme`
- Applies before page render (inline `<script>` in `<head>` of `base.html`) to prevent FOUC
- `computeAccentDerivatives(hex)` auto-generates `--accent-hover`, `--accent-dim`, `--accent-faint`

## Tests

```
uv run pytest tests/ -v
```

Tests are organized into 3 directories with 23 test source files:

**`tests/api/`** (8 files) — Full-stack async HTTP testing via `httpx.ASGITransport` with isolated in-memory SQLite DB:
- `test_characters.py` — CRUD, soft-delete/trash/restore, hard-delete cascade, modal highlight
- `test_chats.py` — CRUD, entity lifecycle (greetings, orphan on character delete), messages
- `test_personas.py` — CRUD, chat lifecycle, modal highlight
- `test_presets.py` — CRUD, default block seeding, lifecycle, cascade on delete
- `test_providers.py` — CRUD for LLM providers
- `test_exchange.py` — Export/import roundtrip (352 lines), granular selection, cascading dependencies, ID remapping, error cases
- `test_stream_abort.py` — Stream failure rollback behavior (new message vs regenerate), monkey-patched provider
- `test_backup.py` — Backup create/list/restore/delete, FileNotFoundError handling

**`tests/units/`** (5 files) — Isolated unit tests:
- `test_utils.py` — `variable_group_name()`, `estimate_image_tokens()`, MIME maps, data URL parsing
- `test_stream_utils.py` — `filter_unsupported_modalities()`, `apply_claude_caching()` (sliding breakpoint, greeting tag, cache_control)
- `test_prompt_chain.py` — `_merge_consecutive()`, `partition_blocks()`, `resolve_variable_blocks()`
- `test_macros.py` — `build_base_macros()` (time-of-day, fallbacks), `extract_setvars()`, `apply_macros()` (substitution, getvar, chain, trim, max-passes guard)
- `test_card_parser.py` — PNG chunk parsing, tEXt/iTXt, V1/V2 card normalisation, error cases

**`tests/frontend/`** (3 Python + 7 JS files):
- `test_frontend.py` — Jinja2 template compilation, asset path validation, critical asset existence, CSS parsing
- `test_js_modules.py` — Node.js subprocess runner for 7 JS test files
- `test_message_template.py` — Server-rendered reasoning button presence/absence in message partial
- 7 JS test files: `test_api_paths.js`, `test_state_manager.js`, `test_message_renderer.js`, `test_reasoning_visibility.js`, `test_abort_cleanup.js`, `test_extract_data.js`, `test_backup_manager.js`

**Infrastructure:** `conftest.py` provides `tmp_test_dir` + `client` (async HTTP with `httpx.ASGITransport`, separate in-memory SQLite per test, full schema + seed). `helpers.py` provides factory functions (`create_character()`, `create_persona()`, etc.) that POST to the API and assert 201.

## Common gotchas

1. **Don't reload the preset selector via HTMX outerHTML swap** after state changes. It races with the DB PATCH. The `@click` handlers update Alpine state synchronously; the PATCH fires async for persistence only. Delete operations should click the fallback item (which calls `StateManager.setPreset`) then remove the deleted DOM node.

2. **`reloadPromptArranger`** is defined in `edit_entity_modal.js` (unconditionally). It now checks `if (!document.getElementById(targetId)) return;` before making the HTMX call, so it's safe to call even when the arranger isn't loaded yet.

3. **`createEditModalHandlers`** (base.html) uses `cfg.stateKey` to find the current entity from StateManager. When reloading modal bodies after edits, always pass `?current_${stateKey}=...` so the active card highlight doesn't vanish.

4. **When adding new modals**, use the `modal_shell` macro. Don't duplicate the overlay/content/header structure. Use the z-index scale vars.

5. **When the arranger is reloaded via HTMX**, the `prompt_arranger.html` script block re-runs. It has a `!_arrangerScriptsLoaded` guard for one-time init (function definitions) + unconditional Sortable init per preset.

6. **Path references:** Jinja `{% include %}` paths are relative to templates/partials dirs. Static files are served from `/static/`. API endpoints are in `window.api` (see `api_paths.js`).

7. **`preserveOpenStates` pattern** — When streaming tokens replaces message content, use `preserveOpenStates(container, renderFn)` to keep reasoning blocks open (`open` class on `.reasoning-block`). Never directly set `innerHTML` on message content during streaming.

8. **AbortController for stream cancellation** — Each generation creates a new `AbortController`. The stop button calls `.abort()`. Canceled streams with no visible text clean up the assistant placeholder div; partial text is preserved.

9. **Message pruning DOM virtualization** — `message_pruner.js` replaces off-screen `.message` nodes with height placeholders (`<div class="message-placeholder" style="height:...px">`). After any HTMX swap affecting messages, call `window.pruneMessages()` or `schedule()`. Always check `window._isMessagePruned(msgId)` before operating on a message DOM node. The streaming message (`window._streamingMessageId`) is excluded from pruning.

10. **Never put `data-action` on a `<form>` element** — The form guard in `actions.js` (`if (el.tagName === 'FORM') return;` on click/change/input) means form actions only fire via the `submit` event listener. Use `onsubmit="fn(event)"` or put `data-action` on the submit button itself. The guard prevents random clicks/keystrokes inside the form from triggering the action and closing modals.

11. **Send/regen mode** — The send button shows a send icon when textarea has content, and a regen icon when textarea is empty + last message role is user. `updateSendButtonState()` handles this. When in regen mode, clicking sends an empty `user_message` with `regenerate: true`.

12. **`ListManager.setup()`** — Config-driven factory that generates named global functions (filter, sort, compact toggle, new item). Don't create separate handlers per entity type. Call it once per modal with the appropriate `cfg` object.

13. **Editor modal z-index** — `var-edit-modal`, `block-edit-modal`, and the preset rename modal all use `--z-modal-high: 1000`. When adding new editor/inline modals, use the same z-index. Sub-modals within provider management use `--z-modal-sub: 100`.

14. **Variables management scripts** — Defined in `chat.html` with a `!_varScriptsLoaded` guard: `updateVarPositions`, `initVarSortables`, `reloadPresetVariables`, `handleVarUpdate`, `handleVarDelete`, `openVarEditModal`, `closeVarModal`, `saveVarModal`. These survive HTMX re-renders of the variable groups partial.

15. **SVG sprite system** — SVG icon macros are defined in `macros.html` (`icon_plus`, `icon_trash`, `icon_close`, etc.). The `#svg-sprite` div in `base.html` renders them into a sprite sheet, accessed via `window.getSvgSprite(name, size)`. Don't add inline SVGs — add macros to `macros.html` and reference them via the sprite.

16. **Hint tooltip system** — A reusable `hint_tooltip(text)` macro in `macros.html` renders a `?` icon. Text is stored in a `data-hint` attribute. On hover, `showHint(el)` in `base.html`'s inline script positions a single global `#hint-tooltip` element (`body` child, `position: fixed`) using `getBoundingClientRect()`. `hideHint()` hides it on leave. No Alpine dependency. CSS selectors: `.hint-wrapper` (relative inline-flex), `.hint-icon` (16x16 circle, cursor:help), `#hint-tooltip` (surface-2 background, border, shadow, z-index overlay+1, font-weight 400). To add a hint: `{{ hint_tooltip('Your explanation here.') }}`. Import: `{% from "macros.html" import hint_tooltip %}`. Example in `sampler_modal.html` lines 477, 502, 519.

17. **Server-side message segmentation** — Messages are pre-processed into typed segments by `focus/core/message_render.py:render_message_segments()`. Called in `crud.py:get_chat_messages()`, so every server-rendered message has `.segments`. Three segment types: `text` (raw content, processed by JS `marked`), `reasoning` (pre-escaped HTML, rendered as `.reasoning-block`), `tool_boundary` (insertion point for tool calls). The first reasoning block (index 0) has no toggle button — it's controlled by the message-level `.reasoning-toggle-btn`. Subsequent blocks get individual `.reasoning-summary` buttons calling `toggleReasoningBlock(this)`. Tool call `<details>` elements start collapsed (no `open`). Template renders tool calls only at first boundary (`ns.tool_rendered` flag).

18. **Tool call boundary markers** — During streaming, `stream.py` inserts `%%%TOOL_BOUNDARY%%%` between iteration texts when the model makes tool calls. Stored in variant content. `render_message_segments` splits on this marker and inserts `tool_boundary` segments. The streaming frontend's `_renderToolCalls` omits `open` attribute and label. Stale `.tool-calls-stream` removed at start of `triggerGeneration`.

19. **`_updateReasoningButton` scope change** — Looks for `.reasoning-block` via `msg.querySelector('.reasoning-block')` (within the whole message), not within `.message-content`. This is necessary because server-rendered segments put `.reasoning-block` as a sibling of `.message-content`, not a child. The JS streaming path still puts them inside `.message-content` (via `renderMessage` html), but the server-rendered refresh path uses the sibling layout.

## File naming conventions

- Templates: `snake_case.html`
- Python modules: `snake_case.py`
- JS modules: `snake_case.js`
- CSS: `style.css`, `tailwind-input.css`, `tailwind.css`
- Partials: nested under `partials/<feature>/`
- Modals: `partials/modals/<name>_modal.html`
- Vendor files: `static/vendor/<name>.min.js` (no version numbers in filenames)
