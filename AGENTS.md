# Focus — Agent Quick Reference

## Stack

FastAPI (async) + aiosqlite | Jinja2 | HTMX 2.x + Alpine 3.x | Tailwind v4 | uv + hatchling | pytest + Node

## Start / Test

- **Start:** `./start.sh` (vendor-sync → tailwind → `uv run main.py`)
- **Test:** `./test.sh` (`uv run pytest`)
- **Tailwind:** `./bin/tailwindcss-linux-x64 -i static/tailwind-input.css -o static/tailwind.css --minify` (agent env can't run — USER must run)

### Venv / musl note

The opencode container runs on Alpine (musl libc), the host may be glibc. Venv symlinks to system Python break when moving between environments. If `uv run` fails with "Broken symlink" or "Failed to inspect Python interpreter", just re-run — `uv` recreates the venv automatically.

## Project structure

```
main.py                    # FastAPI app entry
focus/                     # Backend
  core/                    # Database, models, paths, utils, logger, macros, card_parser, message_render
  providers/               # LLM providers (openai_compat, openrouter, deepseek, moonshot, google_*)
  routers/                 # API routes (pages, chats, characters, presets, providers, personas, stream, tools, settings, exchange, backup)
  tools/                   # Tool system (builtin, external, helpers, provider_adapter)
templates/                 # Full-page Jinja2 templates
partials/                  # HTMX partials (chat/, modals/, personas/, presets/)
static/
  js/core/                 # state-manager, actions, chat-stream, api-paths
  js/features/             # char-editor, backup-manager
  js/messages/             # message-renderer, message-refresh, reasoning-utils, file-staging, edit-message, delete-mode, message-pruner
  js/modals/               # providers, edit-entity, char-edit, persona-edit
  js/ui/                   # theme-manager, list-manager, lightbox, scroll-manager, status-panel, confirm, modal, input-bar, media-utils, notifications
  js/utils/                # claude-cache, set-tracker
  vendor/                  # htmx2, alpine, marked, purify, sortable, cropper, inter
data/                      # focus.db, backups/, assets/
```

## Critical patterns

### StateManager (`static/js/core/state-manager.js`)

Single source of truth (loaded in `<head>`). 5 fields: `character_id`, `persona_id`, `preset_id`, `provider_id`, `provider_type`.

- **Set:** `StateManager.setPreset(id)` / `setCharacter(id)` / `setPersona(id)` / `setProvider(id, type)` — auto-persists (DB for chat fields, localStorage for provider). All accept null.
- **Read:** `StateManager.get('character_id')` or `.getAll()`
- **React:** `StateManager.on('preset-changed', fn)` — callback gets `{ prev, value }`
- **Alpine:** `setPreset`/`setProvider` dispatch `window.CustomEvent` → listen `@preset-changed.window` / `@provider-changed.window`. `setCharacter`/`setPersona` emit listener-only events — register callbacks in `chat.html`.

### Data-action dispatch (`static/js/core/actions.js`)

4 delegated listeners on `document`: click / submit / change / input. `data-action` resolves via `window[name]` or dotted path. **Form guard:** click/change/input skip `<form>` elements — form actions only fire on `submit`. So never put `data-action` on a `<form>`, only on the submit button.

### Modals

- Template: `{% from "modal-shell.html" import modal_shell %} / {% call modal_shell('id', 'Title') %}...{% endcall %}`
- Show/hide: `classList.remove('hidden')` / `add('hidden')` (never `style.display` — `hidden` has `!important`)
- Z-index scale: 50 (base) → 100 (sub) → 1000 (editors) → 10000 (overlays) → 10010 (confirm)
- Editor modals (block edit, var edit, text expander, rename) at z-index 1000

### Streaming

SSE events: `start | token | reasoning | tool_calls | tool_result | done`.

**Frontend** — `stream-events.js`: `StreamState` per generation, `HANDLERS` dispatch via `dispatchStreamEvent()`. `message-builder.js`: `segmentBuilders` factories (text/reasoning/tool_calls). Finalize with `finalizeStreamRender()`.

**Backend** — `_active_generations` maps `message_id → asyncio.Event`. Stop button calls `POST /api/stop-generation/{message_id}` which sets the event — SSE generator drains gracefully instead of `AbortController.abort()`. Both `_stream_generate` (SSE) and `_non_stream_generate` (JSON) share `_run_generation()`.

**Segment rendering** — messages split into `text | reasoning | tool_boundary` typed siblings. `_build_segments()` builds `segments_json` from per-iteration slices, stored in `message_variants`. Never use `fullText` for per-segment rendering. Use `preserveOpenStates()` not `innerHTML` to keep reasoning toggles open.

### Tool system

**Data model** — `ToolSpec`, `ToolParam`, `ToolCall`, `ToolResult` in `focus/tools/__init__.py`.

**Builtin** — `BUILTIN_TOOLS` in `builtin.py`: `read_file`, `list_dir`, `read_image`, `execute_shell`. Each has a `writes` flag for read-only safety.

**External** — JSON configs in `tools/*.json` (gitignored, project root). Format: `ExternalToolConfig(name, description, command, timeout, writes, params)`. Loaded via `load_external_tools()` → `ALL_TOOLS`. Invalid files silently skipped (logged as warning).

**Provider adapter** — `to_provider_tools()` converts `ToolSpec` → OpenAI-compatible `tools=` payload. `to_provider_tool_results()` → tool-role messages.

**Read-only mode** — `active_tools(all_tools, read_only)` filters `writes=True` tools. Checked in `_execute_tool_round()` before calling handlers.

**Iteration loop** — `_run_generation()` loops up to `MAX_TOOL_ITERATIONS`. Per iteration: stream tokens → detect `tool_calls` → break → execute → emit results → loop. Calls persisted to `tool_calls` table.

### Macro system (`focus/core/macros.py`)

**Built-in macros** — defined in two places that must stay in sync:
1. `build_base_macros()` — computes actual values (e.g. `card.get("name", "Assistant")`)
2. `MACRO_DEFINITIONS` dict — metadata (description, source) for the help modal

**Special syntax tokens** (not simple `{{key}}` → value lookups):
- Defined in `SPECIAL_TOKENS` list — `{{getvar::key}}`, `{{setvar::key::value}}`, `{{var::key::value}}`, `{{trim}}`, `{{// comment}}`, `{{media::id}}`

**Adding a new macro:**
1. Add key + resolver to `build_base_macros()` in `macros.py`
2. Add matching key + `{"description", "source"}` to `MACRO_DEFINITIONS`
3. The sync test `TestMacroDefinitions::test_keys_match_build_base_macros` will fail if 1 and 2 drift apart
4. Jinja2 globals `macro_definitions` / `special_tokens` (set in `pages.py:42-43`) auto-pick up changes

**Comment macro** `{{// ... }}` — stripped by `_strip_comment_macros()` before any macro resolution. Depth-aware: counts `{{`/`}}` nesting, so `{{// uses {{char}} }}` is fully stripped. Handles `{{ // ` with whitespace between braces and `//`.

**Template globals** — `macro_definitions` and `special_tokens` are registered as Jinja2 globals in `pages.py:42-43`, available in every template including inline `{% include %}` renders (not just API route responses).

### Continue / prefill architecture

On continue, server emits existing partial content + reasoning as synthetic SSE events (`type: reasoning` / `token`) before real tokens. Frontend sees the complete message — no `prefillMode` needed.

- `_prepare_generation_messages()` appends a prefill assistant message to the API context.
- Stream path emits synthetic events after `start` when `echoes_prefill` is false (DeepSeek, Moonshot).
- Non-stream path prepends prefill to `collected`/`collected_reasoning` before final join.
- Template always renders empty `.message-content` div when msg has reasoning but no text — pulse cursor needs a DOM position.

### Preserve Thinking

Controls whether past assistant reasoning fields are sent in multi-turn history. Set in sampler modal, applied in `_prepare_generation_messages()` (`stream.py:110-133`).

- **off** — strip reasoning from all past assistant messages
- **tool_only** — strip unless the message had `tool_calls` (reasoning from tool-using turns is useful context)
- **all** — keep everything

Only matters for DeepSeek, Moonshot, openai_compat with `include_reasoning` on.

## Critical gotchas

1. **`:last-of-type` is not "last with this class"** — `querySelector('.message:last-of-type')` on `#message-list` fails because `#scroll-sentinel` (same `<div>` tag) is truly last. Use `querySelectorAll('.message')` and take the last NodeList element.

2. **Never set `innerHTML` during streaming** — use `preserveOpenStates(container, renderFn)` to keep reasoning blocks open. Direct `innerHTML` destroys open toggle state.

3. **Message pruning** — `message-pruner.js` replaces off-screen `.message` with height placeholders. After any HTMX swap, call `window.pruneMessages()`. Check `window._isMessagePruned(msgId)` before DOM ops. `window._streamingMessageId` is excluded.

4. **Reasoning-only messages have `.message-content`** — Template renders empty `<div class="message-content markdown-content">` when msg has `reasoning` but no text, so pulse cursor and tokens have a DOM position. JS fallback (create-if-missing) only fires for pre-existing messages.

5. **Alpine `x-show` elements need `x-cloak`** — Alpine loads with `defer`, so there's a gap between HTML parsing and Alpine init. Any full-screen overlay using `x-show="expr"` without `x-cloak` will flash visible during this gap. The preset rename modal (`preset-selector.html:91`) is the prime example. Add `x-cloak` to any new `x-show`-based modals.
