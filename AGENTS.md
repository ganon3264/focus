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
  tools/                   # Tool system (builtin, provider_adapter)
templates/                 # Full-page Jinja2 templates
partials/                  # HTMX partials (chat/, modals/, personas/, presets/)
static/
  js/core/                 # state_manager, actions, chat_stream, api_paths
  js/features/             # char_editor, backup_manager
  js/messages/             # message_renderer, message_refresh, reasoning_utils, file_staging, edit_message, delete_mode, message_pruner
  js/modals/               # modal_providers, edit_entity_modal, modal_char_edit, modal_persona_edit
  js/ui/                   # theme_manager, list_manager, lightbox, scroll_manager, status_panel, confirm, modal, input_bar, media_utils, notifications
  js/utils/                # claude_cache, set_tracker
  vendor/                  # htmx2, alpine, marked, purify, sortable, cropper, inter
data/                      # focus.db, backups/, assets/
```

## Critical patterns

### StateManager (`static/js/core/state_manager.js`)

Single source of truth (loaded in `<head>`). 5 fields: `character_id`, `persona_id`, `preset_id`, `provider_id`, `provider_type`.

- **Set:** `StateManager.setPreset(id)` / `setCharacter(id)` / `setPersona(id)` / `setProvider(id, type)` — auto-persists (DB for chat fields, localStorage for provider). All accept null.
- **Read:** `StateManager.get('character_id')` or `.getAll()`
- **React:** `StateManager.on('preset-changed', fn)` — callback gets `{ prev, value }`
- **Alpine:** `setPreset`/`setProvider` dispatch `window.CustomEvent` → listen `@preset-changed.window` / `@provider-changed.window`. `setCharacter`/`setPersona` emit listener-only events — register callbacks in `chat.html`.

### Data-action dispatch (`static/js/core/actions.js`)

4 delegated listeners on `document`: click / submit / change / input. `data-action` resolves via `window[name]` or dotted path. **Form guard:** click/change/input skip `<form>` elements — form actions only fire on `submit`. So never put `data-action` on a `<form>`, only on the submit button.

### Modals

- Template: `{% from "modal_shell.html" import modal_shell %} / {% call modal_shell('id', 'Title') %}...{% endcall %}`
- Show/hide: `classList.remove('hidden')` / `add('hidden')` (never `style.display` — `hidden` has `!important`)
- Z-index scale: 50 (base) → 100 (sub) → 1000 (editors) → 10000 (overlays) → 10010 (confirm)
- Editor modals (block edit, var edit, text expander, rename) at z-index 1000

### Streaming (`static/js/core/chat_stream.js`)

Messages segmented into `text | reasoning | tool_boundary` typed siblings (mirrors `focus/core/message_render.py:render_message_segments()`). Never use `fullText` for per-segment rendering — each segment has its own div with independent `startThinkIdx`. Each generation creates a new `AbortController`. Stop button calls `.abort()`.

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

When the user continues an interrupted assistant message, the server emits the prefill (existing partial content + reasoning) as **synthetic SSE events** (`type: reasoning` / `token`) before the model's real tokens. This means the frontend receives the *complete* message during streaming — no special `prefillMode` awareness needed.

Key rules:
- The server's `_prepare_generation_messages()` appends a prefill assistant message with `content` and `reasoning` fields to the API context.
- The streaming generator emits the prefill as synthetic events after the `start` event when `echoes_prefill` is false (DeepSeek, Moonshot).
- The non-stream path prepends prefill to `collected` / `collected_reasoning` lists before the final join.
- The template always renders an empty `.message-content` div when a message has reasoning but no text segment — so the DOM structure is consistent and the pulse cursor has a place.

## Critical gotchas

1. **`:last-of-type` is not "last with this class"** — `querySelector('.message:last-of-type')` on `#message-list` fails because `#scroll-sentinel` (same `<div>` tag) is truly last. Use `querySelectorAll('.message')` and take the last NodeList element.

2. **Never set `innerHTML` during streaming** — use `preserveOpenStates(container, renderFn)` to keep reasoning blocks open. Direct `innerHTML` destroys open toggle state.

3. **Message pruning** — `message_pruner.js` replaces off-screen `.message` with height placeholders. After any HTMX swap, call `window.pruneMessages()`. Check `window._isMessagePruned(msgId)` before DOM ops. `window._streamingMessageId` is excluded.

4. **`reloadPromptArranger`** (`static/js/modals/edit_entity_modal.js`) — guards with `if (!document.getElementById(targetId)) return;`, safe to call without arranger loaded.

5. **`message-content` div always present for reasoning-only messages** — the Jinja2 template renders an empty `<div class="message-content markdown-content">` when a message has `reasoning` but no text segment, so the streaming pulse cursor and token rendering have a DOM position. The token handler's JS fallback (`querySelector('.message-content')` then create-if-missing) is a safety net for pre-existing messages, but template-rendered messages always have it.

6. **Alpine `x-show` elements need `x-cloak`** — Alpine loads with `defer`, so there's a gap between HTML parsing and Alpine init. Any full-screen overlay using `x-show="expr"` without `x-cloak` will flash visible during this gap. The preset rename modal (`preset_selector.html:91`) is the prime example. Add `x-cloak` to any new `x-show`-based modals.
