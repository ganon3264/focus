# Focus — Agent Reference

## Stack

FastAPI (async) + aiosqlite | Jinja2 | HTMX 2 + Alpine 3 | Tailwind v4 | uv + hatchling | pytest + Node

## Start / Test

- **Start:** `./start.sh` — vendor sync → tailwind build → `uv run main.py`
- **Test:** `./test.sh` — `uv run pytest`
- **Tailwind:** `./bin/tailwindcss-* -i static/tailwind-input.css -o static/tailwind.css --minify` (must run manually in agent env)

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
    core/                # state-manager, actions, chat-stream, api-paths
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

### Modals

- Template: `modal-shell.html` macro → `{% call modal_shell('id', 'Title') %}...{% endcall %}`
- Show/hide: toggle `hidden` class (not `style.display`)
- z-index layers: base → sub → editors → overlays → confirm (scale by 10× from 50)

### Streaming

SSE events: `start | token | meta | tool_calls | tool_result | done`.

**Frontend:**
- `chat-stream.js` orchestrates: `setGeneratingUI()` → `uploadStagedAttachments()` → `finalizeStreamRender()` → `refreshMessagesAfterStream()`
- `stream-events.js`: `StreamState` per generation, `HANDLERS` dispatch via `dispatchStreamEvent()`
- `message-builder.js`: segment builders for text/reasoning/tool_calls; `finalizeStreamRender()` assembles the DOM
- `generation-ui.js`: toggles send/stop buttons, manages spinner, removes stale content
- `post-process.js`: re-renders markdown, syncs reasoning buttons, updates UI after swap
- Messages split into `text | reasoning | tool_boundary` segments (`segments_json` column). Use `preserveOpenStates()` not `innerHTML` to keep reasoning toggles open.

**Backend:**
- `_active_generations` maps `message_id → asyncio.Event`. Stop via `POST /api/stop-generation/{message_id}`. Both stream (SSE) and non-stream (JSON) share `_run_generation()`.
- Meta events (reasoning, reasoning_details) handled via `TRACKED_FIELDS` in `tracked_fields.py`. Each field has a `merge` mode (`append`/`index`) and `stream_to_sse` flag.
- On continue: server emits existing content as synthetic SSE events before real tokens. `prepare_generation_messages()` appends prefill to API context.

### Tool system

- Data model: `ToolSpec`, `ToolParam`, `ToolCall`, `ToolResult` in `tools/__init__.py`
- Builtin: `read_file`, `list_dir`, `read_image`, `execute_shell`. Each has a `writes` flag for read-only filtering.
- External: JSON configs in `tools/` (recursive scan, 2 levels, skip hidden dirs). Format: `ExternalToolConfig(name, description, command, timeout, writes, params)`.
- Iteration: `_run_generation()` loops up to `MAX_TOOL_ITERATIONS`. Per iteration: stream → detect `tool_calls` → break → execute → emit results → loop.

### Provider system

- Each LLM provider = a module in `providers/` implementing the base interface. `to_provider_tools()` converts ToolSpec → OpenAI-compatible format.
- Frontend: single shared `provider-form` with `prov-form-*` id prefix. Flow: `resetProviderForm()` → `populateProviderForm(data)` → `extractData(form)` for PATCH/POST.
- OpenRouter: option pickers use Alpine `modal-select-option`; route/quant stored in hidden inputs.

### Macros (`focus/core/macros.py`)

- Built-in macros: `build_base_macros()` (values) and `MACRO_DEFINITIONS` (metadata). Must stay in sync — test `TestMacroDefinitions::test_keys_match_build_base_macros` enforces this.
- Special tokens: `{{getvar::key}}`, `{{setvar::key::value}}`, `{{var::key::value}}`, `{{trim}}`, `{{// comment}}`, `{{media:id}}`
- Comments `{{// ...}}` stripped pre-resolution, depth-aware for nesting.
- Template globals `macro_definitions`/`special_tokens` registered in `pages.py`.

## Common gotchas

- **`x-show` needs `x-cloak`** — Alpine loads `defer`, so overlays using `x-show` without `x-cloak` flash visible during HTML parsing.
- **`:last-of-type` isn't "last with this class"** — the scroll sentinel shares the same tag. Use `querySelectorAll('.message')` and take the last NodeList element.
- **Call `window.pruneMessages()` after HTMX swaps** — `message-pruner.js` replaces off-screen messages with placeholders. Check `window._isMessagePruned(id)` before DOM ops. `window._streamingMessageId` is excluded.
