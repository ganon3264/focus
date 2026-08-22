# Focus — Agent Reference

## Stack

FastAPI (async) + aiosqlite | Jinja2 | HTMX 2 + Alpine 3 | Tailwind v4 | uv + hatchling | pytest + Node

## Start / Test

- Start: `./start.sh` — vendor sync → tailwind build → `uv run main.py`
- Test: `./test.sh` — `uv run pytest`

## Structure

```
main.py                  # FastAPI app entry
focus/                   # Backend package
  core/                  # DB init, models, utils, macros, segments, media, tracked_fields
  db/                    # CRUD per domain (characters, chats, personas, presets, providers, etc.)
  providers/             # LLM providers (openai_compat, openrouter, deepseek, moonshot, google_*)
  routers/               # Route handlers (pages, chats, stream, presets, providers, tools, backup, etc.)
  tools/                 # Builtin + external tool system, executor, provider adapter
  crud.py, exchange.py, prompt_chain.py, backup.py
templates/               # Full-page Jinja2 templates
partials/                # HTMX fragments (chat/, modals/, personas/, presets/)
static/
  css/                   # Custom CSS modules
  js/
    core/                # state-manager, actions, generation-session, chat-controls, api-paths
    messages/            # Streaming, rendering, editing, pruning
    modals/              # Config forms, editors
    ui/                  # Theme, scroll, lightbox, notifications, etc.
    features/            # char-editor, backup-manager
    utils/               # Small helpers
    vendor/              # HTMX, Alpine, marked, purify, etc. (synced by vendor-sync.py)
assets/                  # User uploads (attachments, characters, personas, tool configs)
data/                    # focus.db, backups/
tools/                   # External tool JSON configs (samples/ shipped)
tests/                   # api/, units/, frontend/ (JS via Node)
```

## Critical patterns

### State flow — `static/js/core/state-manager.js`

Single source of truth for `character_id`, `persona_id`, `preset_id`, `provider_id`, `provider_type`.
- Set via `.setCharacter(id)` / `.setPersona(id)` / `.setPreset(id)` / `.setProvider(id, type)` — auto-persists to DB (chat fields) or localStorage (provider). All accept null.
- Read via `.get('key')` or `.getAll()`.
- React via `.on('event', fn)` — callback gets `{ prev, value }`. Alpine: listen `@event.window`.

### Action dispatch — `static/js/core/actions.js`

`data-action="fnName"` on elements → delegated `document` listeners (click, submit, change, input).
- **Form guard**: only `submit` events trigger actions on forms. Never put `data-action` on `<form>`.
- Message toolbar buttons read context from `el.closest('.message')` data-* attributes (no inline JS).

### Modals (`static/js/ui/modal.js`)

- Single lifecycle controller: `ModalController.open(id)` / `close(id, opts)` / `closeTop()` / `isOpen(id)` / `isDirty(id)` / `setDirty(id, bool)` / `refresh(id)` / `onOpen(id, fn)`. Globals `openModal(id)` / `closeModal(id, opts)` are thin wrappers.
- Template: `modal-shell.html` macro → `{% call modal_shell('id', 'Title') %}...{% endcall %}`
- Show/hide: toggle `hidden` class (not `style.display`) — done by the controller, never manually.
- z-index layers: base → sub → editors → overlays → confirm (scale by 10× from 50)
- **Dirty tracking is opt-in via overlay attributes** (rendered by `modal_shell` params `dirty_fields`, `dirty_label`): snapshot is captured automatically on open (fields created before/at open are baselined; fields added later are lazily baselined). `[data-dirty-hint]` gets `.hidden`, `[data-dirty-save]` gets `.disabled` + `.opacity-50`. State changes dispatch `dirty-changed` on `window` (`{id, dirty}`) — used by the rename-preset modal's Alpine UI.
- Closing a dirty modal prompts via confirm; **save handlers must call `closeModal(id, {discard: true})`** (never `captureDirty`-style resets). Use `ModalController.setDirty(id, true)` for non-field changes (e.g. attachment add/delete).
- ESC closes: confirm modal (as Cancel) → topmost modal → lightbox. `option-selected` / `custom-select:set` trigger recompute of open modals.
- Overlays inside htmx-swapped bodies (providers modal) re-register automatically on open.

### Toast system (`static/js/ui/notifications.js`)

- One stack: `#toast-container` in `base.html` (fixed top-center, `z-index: var(--z-max)`, above all modals).
- API: `showToast(msg, {type, duration})`, aliases `showInfoToast` (accent, 3s), `showSuccessToast` (green, 3s), `showErrorToast` (danger, persists with Copy/Close), `showImportToast(data, pluralLabel)` (shared import report: error list or success count), `hideErrorToast()`, `hideInfoToast()`, `hideAllToasts()`.
- `notifications.js` is loaded in `base.html` above `{% block content %}`, so the API is always defined on every page — call it unguarded.
- All cards stack as a list; per-card timer with hover-pause; dedup by type+message (refreshes timer); max 5 visible (oldest evicted); fade in/out via `toast-in`/`toast-out` in `animations.css`. Never block with `alert()` — use toasts.

### Streaming

SSE payloads are uniform envelopes — always `{"type": "<event>", ...}` with events
`start | token | meta | tool_calls | tool_result | done | error`. Dispatch is a
table lookup (`HANDLERS[json.type]`); unknown types log a warning, never vanish silently.

**Ownership:** cross-module state goes through the module that owns it
(`StateManager` for ids, `Generation` for the generation lifecycle) — never
`window._foo` handoffs.

**Frontend:**
- `core/generation-session.js`: single owner of the generation lifecycle —
  AbortController, active flag, streaming message id, SSE read loop, and the
  stop-escalation ladder. API: `Generation.begin(chatId, asstDiv, opts)` /
  `Generation.stop()` / `.isActive()` / `.streamingId()`.
- **Stop contract:** stop = POST `/api/stop-generation/{id}` (with its own 4s
  timeout) and wait for the normal `done` event; if the POST fails or no `done`
  arrives within 8s, the client hard-aborts. That is safe: Starlette cancels
  the SSE generator on disconnect, which persists partials server-side.
  Feedback via toasts ("Stopping…" → "Generation stopped").
- `ui/chat-controls.js`: send-button glue (builds user message div, calls
  `Generation.begin`).
- `stream-events.js`: `StreamState` per generation, `HANDLERS` dispatch via
  `dispatchStreamEvent()`. Handlers record outcomes on the state object
  (`state.done`, `state.errorMsg`) — they never throw.
- Token renders are rAF-coalesced (one markdown pass per frame, trailing
  edge); `finalizeStreamRender()` force-flushes before the post-stream refresh.
- `message-builder.js`: segment builders for text/reasoning/tool_calls.
- `generation-ui.js`: toggles send/stop buttons, spinner, `clearStaleContent()`.
- `post-process.js`: re-renders markdown, syncs reasoning buttons, updates UI
  after swap (also owns the `htmx:afterSwap` hook).
- Messages split into `text | reasoning | tool_boundary` segments (`segments_json` column). Use `preserveOpenStates()` not `innerHTML` for **in-place re-renders** (e.g. streaming segment updates) to keep reasoning toggles open; fresh nodes swapped in from the server start collapsed by design — do not preserve state across server swaps.
- **Continue invariant:** the stream always delivers the complete text —
  providers with `echoes_prefill=True` resend the partial themselves, others
  get it synthesized server-side. The frontend never seeds content; on
  continue it binds the existing `.message-content` div as an empty first
  segment so tokens replace its contents in place.

**Backend:**
- `_active_generations` maps `message_id → asyncio.Event`. Stop via `POST /api/stop-generation/{message_id}`. Both stream (SSE) and non-stream (JSON) share `_run_generation()`.
- Meta events (reasoning, reasoning_details) handled via `TRACKED_FIELDS` in `tracked_fields.py`. Each field has a `merge` mode (`append`/`index`) and `stream_to_sse` flag; only `stream_to_sse` fields reach the wire as `meta` events.
- Mid-stream partial saves are wall-clock driven: `_maybe_checkpoint()` writes at most once per `_CHECKPOINT_INTERVAL_SECS` (independent of provider speed and reply length), forced at tool boundaries and on done/error.
- On continue: `prepare_generation_messages()` appends the prefill to API context; for non-echo providers `_run_generation_with_prefill()` synthesizes the existing content as SSE events before real tokens.
- `echoes_prefill` is a per-provider-*type* default (openai_compat=True), not a per-server fact — known sharp edge for endpoints that behave differently than their type suggests.

### Tool system

- Data model: `ToolSpec`, `ToolParam`, `ToolCall`, `ToolResult` in `tools/__init__.py`
- Builtin: `read_file`, `list_dir`, `read_image`, `execute_shell`. Each has a `writes` flag for read-only filtering.
- External: JSON configs in `tools/` (recursive scan, 2 levels, skip hidden dirs). Format: `ExternalToolConfig(name, description, command, timeout, writes, params)`.
- Iteration: `_run_generation()` loops up to `MAX_TOOL_ITERATIONS`. Per iteration: stream → detect `tool_calls` → break → execute → emit results → loop.

### Provider system

- Each LLM provider = a module in `providers/` implementing the base interface. `to_provider_tools()` converts ToolSpec → OpenAI-compatible format.
- Frontend: single shared `provider-form` with `prov-form-*` id prefix. Flow: `resetProviderForm()` → `populateProviderForm(data)` → `extractData(form)` for PATCH/POST.
- Option pickers (OpenRouter route/quant, character theme, ...): **one shared searchable picker** — `partials/modals/option-picker.html` (included last in `chat.html`; always in DOM, stacks above all modals) + `static/js/ui/option-picker.js` exposing `openOptionPicker(options, title, cb)`. Values land in hidden inputs + display spans.

### Theme system

- Themes live in the `themes` table (built-ins seeded as `is_system` rows with fixed ids `builtin-*`; custom themes CRUD via `/api/themes`). Built-ins are editable in place; `POST /api/themes/{id}/reset` restores their canonical seed values; only custom themes can be deleted.
- **Pair model**: two global slots — `dark_theme_id` + `light_theme_id` in settings, written via `PUT /api/settings/theme {slot: 'dark'|'light', theme_id}`. The app always follows `prefers-color-scheme`; effective = `characters.theme_id ?? (dark ? dark slot : light slot)`. Want "always dark"? Set both slots to the same theme.
- `chat_page` embeds `window.THEMES` + `window.THEME_STATE` server-side; `theme-manager.js` applies, caches both slot palettes to `focus-theme-state` (flash-free pre-paint in `base.html`), re-resolves on `matchMedia` change, `character-changed`, and `character-edited` events. Action feedback via the toast system (`showToast` in `notifications.js`, container `#toast-container` in `base.html`).
- Theme modal (`partials/modals/theme.html`): clicking a row selects it for editing; per-row Dark/Light buttons assign the slots (mutually exclusive, `.slot-btn.slot-active`); "New" creates the theme immediately from the typed name + current picker colors (toast, stays open, new theme selected). Live picker preview is NOT saved: `dirty` state (name/pickers vs stored values) enables Save, shows an "Unsaved changes" hint, and prompts before switching themes (`switchTo` + `openConfirmModal`).

### Macros (`focus/core/macros.py`)

- Built-in macros: `build_base_macros()` (values) and `MACRO_DEFINITIONS` (metadata). Must stay in sync — test `TestMacroDefinitions::test_keys_match_build_base_macros` enforces this.
- Special tokens: `{{getvar::key}}`, `{{setvar::key::value}}`, `{{var::key::value}}`, `{{trim}}`, `{{// comment}}`, `{{media:id}}`
- Comments `{{// ...}}` stripped pre-resolution, depth-aware for nesting.
- Template globals `macro_definitions`/`special_tokens` registered in `pages.py`.

## Common gotchas

- **`x-show` needs `x-cloak`** — Alpine loads `defer`, so overlays using `x-show` without `x-cloak` flash visible during HTML parsing.
- **`:last-of-type` isn't "last with this class"** — the scroll sentinel shares the same tag. Use `querySelectorAll('.message')` and take the last NodeList element.
- **Call `window.pruneMessages()` after HTMX swaps** — `message-pruner.js` replaces off-screen messages with placeholders. Check `window._isMessagePruned(id)` before DOM ops. The streaming message (`Generation.streamingId()`) is excluded.
