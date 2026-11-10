# Focus — Agent Reference

## Stack

FastAPI (async) + aiosqlite | Jinja2 | HTMX 2 + Alpine 3 | Tailwind v4 | uv + hatchling | pytest + Node

## Start / Test

- Start: `./start.sh` — vendor sync → tailwind build → `uv run main.py`
- Test: `./test.sh` — `uv sync --locked --group dev`, then `uv run pytest tests/ -v` with coverage (`--no-cov` skips it)

## Structure

```
main.py                  # FastAPI app entry
focus/                   # Backend package
  core/                  # DB init, models, utils, macros, segments, media, tracked_fields,
                         # regex/structured, summary, retry, progress_stream, request_transforms
  db/                    # CRUD per domain (characters, chats, personas, presets, providers, etc.)
  providers/             # LLM providers (openai_compat, openrouter, deepseek, moonshot, xiaomi_mimo, google_*)
  routers/               # Route handlers (pages, chats, stream, stream_utils, presets, providers, tools, backup, …)
  tools/                 # Builtin + external tool system, executor, provider adapter
  extensions/            # Extension loader / runner / triggers
  crud.py, exchange.py, exchange_remap.py, exchange_sanitize.py, prompt_chain.py, backup.py
templates/               # Full-page Jinja2 templates
partials/                # HTMX fragments (chat/, modals/, presets/)
static/
  css/                   # variables, tokens, base, animations, surfaces/*, primitives
  js/
    core/                # state-manager, refresh, actions, hx-queue, generation-session,
                         # selection, provider-schema/store, sse, api-paths
    messages/            # Streaming, rendering, editing, pruning, identity
    modals/              # Config forms, editors, char blocks
    ui/                  # modal, confirm, notifications, theme, scroll, lightbox,
                         # chat-controls, option-picker, input-bar, status-panel
    features/            # backups, extensions, presets, preset-variables, regex, structured
    utils/               # set-tracker, claude-cache, timestamp-formatter
  vendor/                # HTMX, Alpine, marked, purify, sortable, cropper (synced by vendor-sync.py)
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

### Live updates — `static/js/core/refresh.js`

Single source of truth for "a resource changed → reload every surface that renders it". Mutation sites declare what they wrote; nobody hand-wires reloads. Loaded in `base.html`'s shared core block.

- `Refresh.changed(...resources)` — coalesces within a tick, resolves the surfaces whose `deps` include a resource, drops `covers`-ed ones, runs their `load()`. Never call `changed()` from a loader (recursion).
- `Refresh.mutate(url, opts, { changed })` — runs the write through `hxFetch` (shared queue) and invalidates only when `res.ok`.
- `Refresh.load(surface)` — explicit load (Advanced-modal tabs on open); ignores `when`.
- Surface shape `{ deps, load, guard?, when?, covers? }`: `guard: 'not-streaming'` skips during generation (owned centrally — don't re-check `Generation.isActive` per feature); `when` gates flush (e.g. modal open); `covers` names surfaces the loader already re-renders. Resources are the entity families in `RESOURCES`; a `changed()` for an unclaimed resource warns in dev (`window.DEBUG`).
- Selection changes (`applyPreset/Character/Persona` in `core/selection.js`) fan out through it after the persist PATCH — preset/character/persona all re-render the message list, because preset display regex and macro resolution feed it. The Advanced modal's `onOpen` uses `Refresh.load` for tools/extensions/regex/structured/backups; those loaders are exposed by the Alpine components as `window.reloadToolsState` / `window.reloadExtensionsState` (or the existing `window.reload*`).
- In-place list editors (regex/structured rows, tools/extensions toggles) stay explicit on purpose — the registry is coarse, and targeted row swaps avoid a full-list flash on every field blur. A backup restore is the one "replace arbitrary entities" op and hard-reloads (`backup-manager.js`), mirroring import.
- **Entity-card grids and message toolbars are surfaces too.** `characterCards` / `personaCards` (`deps: ['characters'|'personas']`, gated on `modal-characters`/`modal-personas` being open) re-fetch through `window.reloadCharacterCards` / `window.reloadPersonaCards` (`ui/modal.js`), so an active edit/delete no longer needs an ad-hoc per-card `hxGet` (`edit-entity.js`, `shared-entity-modal.js` fall back to it only when the registry is absent or the edited row is not active). `messageToolbars` (`deps: ['extensions']`) patches only each live message's `.toolbar` in place (`message-refresh.js::refreshMessageToolbars`) instead of swapping whole server nodes — a full swap would collapse every open reasoning block.

### Message identity — `static/js/messages/message-identity.js`

Single source of truth for message id translation. A message is identified by its **bare** id, carried on the node as `data-message-id`. Two derived forms are never written by hand:
- DOM node `#message-<id>` → `MessageIdentity.domId(id)` / `MessageIdentity.node(id)`
- pruned stub `.message-placeholder[data-msg-id="<id>"]` → `MessageIdentity.placeholder(id, root)`

The pruner's `_pruned` map is keyed by bare id (`MessageIdentity.bare`); `_forgetPruned(id)` drops a stale entry. All id reads/writes in `message-pruner.js`, `message-refresh.js`, `stream-events.js`, and `core/actions.js` go through this module.

### Action dispatch — `static/js/core/actions.js`

`data-action="fnName"` on elements → delegated `document` listeners (click, submit, change, input).
- **Form guard**: a `data-action` on a `<form>` fires only for `submit` — the click/change/input listeners skip form elements, so the form's action is its submit handler (provider form, new-key form).
- Message toolbar buttons read context from `el.closest('.message')` data-* attributes (no inline JS).

### Modals (`static/js/ui/modal.js`)

- Single lifecycle controller: `ModalController.open(id)` / `close(id, opts)` / `closeTop()` / `isOpen(id)` / `isDirty(id)` / `setDirty(id, bool)` / `refresh(id)` / `onOpen(id, fn)`. Globals `openModal(id)` / `closeModal(id, opts)` are thin wrappers.
- Template: `modal-shell.html` macro → `{% call modal_shell('id', 'Title') %}...{% endcall %}`
- Show/hide: toggle `hidden` class (not `style.display`) — done by the controller, never manually.
- z-index layers: `--z-modal` 50 → `--z-modal-sub` 100 → `--z-overlay` 10000 → `--z-max` 10010. A shell that must stack over its opener carries an explicit `z_index` (100 editors, 200 nested forms, 1000 text expander, 2000 macro reference) — there is no ×10 ladder.
- **Dirty tracking is opt-in via overlay attributes** (rendered by `modal_shell` params `dirty_fields`, `dirty_label`): snapshot is captured automatically on open (fields created before/at open are baselined; fields added later are lazily baselined). `[data-dirty-hint]` gets `.hidden`, `[data-dirty-save]` gets `.disabled` + `.opacity-50`. State changes dispatch `dirty-changed` on `window` (`{id, dirty}`) — used by the theme customizer's Alpine UI.
- Closing a dirty modal prompts via confirm; **save handlers must call `closeModal(id, {discard: true})`** (never `captureDirty`-style resets). Use `ModalController.setDirty(id, true)` for non-field changes (e.g. attachment add/delete).
- ESC closes: confirm modal (as Cancel) → topmost modal → lightbox. `option-selected` / `custom-select:set` trigger recompute of open modals.
- Overlays inside htmx-swapped bodies (providers modal) re-register automatically on open.
- **Advanced modal** (`modal-advanced` in `partials/chat/modals.html`) is a tab container (`.modal-tabs` + the `tab_bar()` macro) holding Tools, Extensions, Regex, Structured and Backups; each tab body is its own banded chassis. The three old per-feature modals no longer exist; body partials are `modals/tools.html`, `modals/extensions.html`, `modals/regex.html`, `modals/structured.html`, `modals/backup-body.html`. Tabs are pure Alpine `x-show` over statically-included bodies, so the Tools/Extensions components still initialise once at page load; the list tabs (regex, structured, backups) reload once per modal open via `ModalController.onOpen('modal-advanced')` — not on tab click.

### Character editor + custom blocks

- `partials/modals/edit-entity.html` renders both the character and the persona editor (`prefix`, `show_theme`, `show_greetings`). Two panes, each naming its groups with a `.rail`: **Identity** (Portrait, Name / Group / Theme and Media as `.row.setting.labeled.tight` rows sharing one caption/control column) and the content pane (**Description**, **Greeting**). The media row's control is a `.well` grid of 48px cells at a fixed 176px height, scrollable, aligned on both edges with the text inputs above; the create tile is its last cell. Rails carry the readouts and the verbs — description char count + expand key, greeting `n/m` + prev/next/add/delete/expand. There is no divider between the panes; the gutter and the rails are the structure, and the identity pane ends where its content ends (`align-self: start`, scrolls only when the legacy fields open).
- The extras follow the identity fields (they are not floor-anchored): the **Custom blocks** door row, then the **legacy card fields** disclosure — Personality / Scenario / Example dialogue, `<details class="disclosure rowlike">` (row head, not a plated panel), tagged `legacy`, closed by default. They are the old character-card format; the description is what Focus sends, so they are demoted, not removed.
- Card fields are **inside the form**, so they submit with everything else (`PATCH /api/characters/{id}` merges them into `card_json`). They are dirty-tracked like the visible fields.
- Custom blocks are their own modal (`partials/modals/char-blocks.html` → `char-blocks-list.html` → `char-block-item.html`), opened from the door on top of the editor (`z_index='200'`). The list follows the arranger anatomy (`.arranger-item` / `.arranger-header` / `.grip` / `.arranger-title-group` / `.arranger-body` / `.arranger-media`); every edit saves immediately — there is no Save verb.
- `static/js/modals/char-blocks.js` owns it: list is server-rendered (`GET /partials/char-blocks/{char_id}`), a single row re-renders from `GET /partials/char-block/{char_id}/{block_id}`, ordering posts `{ids}` to `POST /api/characters/{char_id}/blocks/reorder`. Every write goes through `hxFetch` — raw `fetch` lets two field edits commit out of order.
- Wire the sortable and the count from `htmx:afterSwap` on `#char-blocks-container`; the `hxGet` promise resolves **before** the swap, so initialising there attaches Sortable to a node about to be replaced.
- The count on the door comes from `data-char-blocks` on the card's edit button; the modal re-syncs it after every load (`syncCount`).
- Blocks are prompt-side only (the preset's `char_blocks` sentinel splices them in), so editing one does not invalidate the message list.

### Message editor + text expander

- `modal-edit-message` (`partials/modals/edit-message.html` + `static/js/messages/edit-message.js`) renders one `.msg-block` per segment: a `.rail` head (name + length readout + expand key) over an auto-sized textarea. Reasoning starts `.collapsed` (rail stays, textarea hides) — the toggle is a caret key in the rail, `actionToggleEditBlock`, not a `<details>`, so the expand key inside the rail cannot toggle the block as a side effect. Tool boundaries render their cards under a "Tool calls" rail.
- Attachments are a rail + a `.well` tray; `#edit-msg-media` is the drop zone **and** the media gallery (`.well.media-row.msg-attachments-tray`), `#edit-msg-attachments` is `display: contents` so its thumbs are the tray's grid items, and `#edit-msg-att-empty` is the static empty note that spans the tray (JS only toggles `.hidden`). A thumb opens the lightbox, like the entity editor's media grid. Unlike the entity editor's fixed three-row gallery, this one hugs its rows (one row minimum, 176 cap).
- `modal-text-expander` is the generic expanded editor: one pane-filling `.field.sized.edit-text`, a foot with the live length readout and an indigo **Done**. It writes into the host field on every keystroke (dispatching `input`), so its own host's dirty tracking still fires.

### Banded modals — every list modal

- A modal whose body is a list is a chassis of bands, not one scroll island:

  | class | role |
  |---|---|
  | `.modal-bands-shell` (`modal_shell(overlay_class=…)`) | tints the title bar into the chrome |
  | `.modal-bands` | the flex column inside `.modal-body` |
  | `.modal-band-head` | readout rail: count + the collection's verbs |
  | `.modal-band-toolbar` | optional search / filter / sort row |
  | `.modal-band-lane` | the one scrolling plane — paints `--surface`, opens with a groove |
  | `.modal-band-foot` | optional closing verb row (Trash Bin, Add Block) |

- Bands pull out to the panel's inner edges with `margin-inline: calc(-1 * var(--modal-pad))` and pad back in, so grooves and plane edges run full width while the content keeps the modal's one inset. The shell zeroes the body's `padding-block` and the bands carry the edges, so the head band sits one `--band-pad` under the title groove and the last band one above the floor.
- **Vertical rhythm is one rule: `--band-pad` (16) above and below every band, no gaps between bands.** Nothing else authors vertical spacing. `grid-audit.js` enforces the number.
- Chrome (title bar + head/toolbar/foot bands) is one tint (`--ink-1`); the lane is the only thing painting a different value. A lane that is the last child closes on the panel floor (`:last-child` rule).
- No scroll fade on the lane: the plane boundary is the edge. `scrollbar-gutter: auto` so the bar rides the lane's padding instead of pushing the rows off the inset.
- Users of the vocabulary: characters, personas, providers, presets, saved keys, trash bin, custom character blocks, prompt itemizer, prompt arranger, sampler, theme customizer, and each Advanced tab (Tools · Extensions · Regex · Structured · Backups). The stacked forms (provider create/edit, edit entity, edit message, summary, export, regex/structured items, text expander) are deliberately not banded — a form is not a collection.
- `grid-audit.js` measures the rhythm on characters, personas, providers, saved keys, model picker, presets, itemizer, arranger, samplers, Advanced and themes: rail on the modal inset, rail one band pad under the title groove, one band pad before the next band, first row one band pad into the lane, last band on the panel floor, foot verb on the inset.
- A rail's last action must be `flush` (`.rail-actions.flush`) when it is a labelled `.btn` — the default optical pull would push it past the modal inset.
- **Counts live in the rail, outside the swap target.** Update them from `htmx:afterSwap` keyed on the lane/target id, never from the `hxGet` promise (it resolves before the swap) — `arranger-count` and the block door's count work this way.
- Block rows (arranger, custom blocks): the role is the **grip's** fill (`.grip.role-*`), not a coloured left edge on the row — the handle is the thing you grab, so the cue belongs on it. Sentinel rows (chat history, character blocks) keep a neutral grip.
- A block's expanded body is **one column**, `.arranger-expand`: `padding: 8 8 8 20` (20 puts every child under the block title, past the grip and caret; 8 is the row's own content edge) and `gap: 8`. Nothing inside it adds a margin — the select | preview row, the in-chat controls row, the depth/order row and the media tray all start and end on that box. Sub-rows inside it are `.row.flat` so their labels land on the same left edge as the title.
- That body is readouts, not fields: the content and reasoning previews are one line (`overflow: hidden; nowrap; ellipsis`), **control height** (`--control-h`, padding taking up the line difference) so they share both edges with the role picker beside them, and open the editor modal on click; the media tray is a 32px slot (`--thumb-size` on `.arranger-media`, add tile `.key.lg`).
- **A row missing its last verb reserves the slot** (`verb_slot()` from macros.html → `.key.sm.slot-empty`): the chat-history row has no delete, and the in-chat row only has a toggle, so without the slot their switch slides 28px right of every other row's.
- Entity rows: `.row.entity-row` in two column-major lanes (`.entity-list`, `column-rule` between them). `reveal-verbs` makes the row's keys appear on hover (characters/personas); without it they stay visible (providers, where the row's edit key is the primary verb).
- Rows: avatar → `.row-title` → `.row-meta` (the group as a `.tag`, blank when ungrouped) → `.row-actions`. A favourite's star stays lit at rest because it is state, not a verb.
- **Providers are one column, two lines**: `.provider-row` (48px) holds an `.entity-identity` stack (name over `type · model`) then the balance readout and the verbs. Presets share the stack (`.preset-row`). Four items on one baseline was unreadable at 2-up width. The 48px height takes `.entity-row.provider-row` because `.row` is 32 and arrives last.

### Toast system (`static/js/ui/notifications.js`)

- One stack: `#toast-container` in `base.html` (fixed top-center, `z-index: var(--z-max)`, above all modals).
- API: `showToast(msg, {type, duration|id, maxChars})`, aliases `showInfoToast` (accent, 3s), `showSuccessToast` (green, 3s), `showErrorToast` (danger, persists with Copy/Close), `showImportToast(data, pluralLabel)` (shared import report: error list or success count), `hideErrorToast()`, `hideInfoToast()`, `hideToast(id)`, `hideAllToasts()`.
- `maxChars` is opt-in visual truncation (appends `…`); the full text stays on the card so the error toast's Copy action is never truncated.
- `notifications.js` loads in `base.html`'s shared script block (after the page content, before any page script), so the API is defined before every caller — call it unguarded.
- All cards stack as a list; per-card timer with hover-pause; dedup by `id` when given, else by type+message (refreshes timer and updates the text in place); max 5 visible (oldest evicted); fade in/out via `toast-in`/`toast-out` in `animations.css`. Never block with `alert()` — use toasts.

### Long-running maintenance — progress stream

- Slow maintenance actions (backup create, clean DB) answer `text/event-stream` and report stages while they run. Backend: `focus/core/progress_stream.py::progress_stream(run)` runs `run(progress)` in a task and streams `progress | done | error` (same envelope as generation; `done` carries `result`). The work function takes an async `progress(label, current=0, total=0)` callback — `clean_database()` and `export_data()`/`create_backup()` accept one.
- Frontend: `static/js/core/sse.js` owns the wire side — `window.readEventStream(response, onPayload)` is the **only** SSE read loop (generation, summarize and progress all use it; returning `true` stops reading and cancels the connection) and `window.streamProgress(url, opts, onEvent)` layers the `progress | done | error` interpretation on top (resolves with the `done` result, rejects on `error` or a truncated stream). A progress caller renders **one id-keyed live toast** (`showInfoToast(..., {id, duration: 0})`), then `hideToast(id)` and a success/error toast on completion. Never fake progress by mutating button labels.

### Streaming

SSE payloads are uniform envelopes — always `{"type": "<event>", ...}`. The wire carries
`start | token | meta | retry | tool_calls | tool_result | extension | debug | done | error`
(reasoning rides `meta` with `field: "reasoning"`). `usage` and `superseded` stay
internal to `_run_generation`/`_handle_event` — usage becomes a DB row, a superseded
run closes silently. Dispatch is a table lookup (`HANDLERS[json.type]`); unknown
types log a warning, never vanish silently.

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
- `message-builder.js`: segment builders for text/reasoning/tool_calls. Message
  chrome has exactly one markup source — the macros in `templates/macros.html`,
  rendered once into inert `<template>`s by `partials/chat/message-templates.html`.
  The builder only clones and fills; it never authors markup. The JS tests clone
  from `tests/frontend/fixtures/message-templates.html`, kept in sync by
  `test_message_template.py::test_message_templates_fixture_is_current`.
- `generation-ui.js`: toggles send/stop buttons and `clearStaleContent()`. The pre-first-token pending state is markup-side (`message-builder.js`: `showMessagePending`/`hideMessagePending`) — the rail carries a spinner + readout while the empty body stays out of the layout. The ticker's phase (`is-waiting` → `is-reasoning` → `is-content`) changes both its hue (`--tick-color`) and its tempo (`--tick-rate`, applied as `playbackRate` by `applyTickRate` — a CSS duration change would restart the track instead of continuing it).
- `message-refresh.js` owns the message-list DOM: `refreshMessageList(chatId, changedIds)` fetches the server partial and reconciles it in place (reorder / reuse / insert / drop), preserving scroll, open reasoning, and pruned stubs. `refreshMessagesAfterStream` and `refreshChatMessages` delegate to it; `refreshSingleMessage` is the cheap one-node path (swipe/edit) with a full-reconcile fallback. All partial fetches go through `hxFetch` so they share one serializer with `hxGet`/`hxPost`.
- `post-process.js`: `processMessageList(container)` is the single post-render pass (markdown, reasoning, timestamps, delete-mode visibility, toolbar state, sentinel). The list reconciler calls it — `refreshMessageList` after every server swap and `refreshSingleMessage`'s node path — and the streaming path reaches it the same way, through the post-stream refresh. It is not an htmx event handler.
- Messages split into `text | reasoning | tool_boundary` segments (`segments_json` column). Use `preserveOpenStates()` not `innerHTML` for **in-place re-renders** (e.g. streaming segment updates) to keep reasoning toggles open; fresh nodes swapped in from the server start collapsed by design — do not preserve state across server swaps.
- **Continue invariant:** the stream always delivers the complete text —
  providers with `echoes_prefill=True` resend the partial themselves, others
  get it synthesized server-side. The frontend never seeds content; on
  continue it binds the existing `.message-content` div as an empty first
  segment so tokens replace its contents in place.

**Backend:**
- `_active_generations` maps `message_id → _ActiveGeneration` (`chat_id`, `provider_id`, stop event, `superseded`). Stop via `POST /api/stop-generation/{message_id}`. Registering a generation supersedes any other in the same chat; editing/deleting a provider stops its active generations (`stop_generations_for_provider`). Both modes share `_run_generation()`. The sampler toggle `stream_enabled` is translated to the provider's `stream` kwarg by `stream()`; `false` (`_non_stream_generate`) makes the provider call non-streaming, keeps the same SSE transport, buffers server-side and replays the finished text as one `token` before `done` — so retry/error feedback still reaches the client while no partial content is ever shown (important for providers whose safety filtering differs when streaming).
- Non-stream is NOT a separate JSON response: `/api/stream` always answers `text/event-stream`. The client only distinguishes buffered vs live by what the server emits.
- Auto-retry (`focus/core/retry.py` + `_run_generation`): provider failures that occur before the first token are retried server-side with backoff, honoring `Retry-After`; once any token/meta has streamed the failure is surfaced instead (a replay would duplicate output). Config is per-provider in `config_json["retry"]` (toggle + advanced; `params_json` holds sampler defaults only); each retry emits a `retry` SSE event (`attempt`, `max`, `delay`, `kind`, `status`, `reason`) that the frontend renders as one live multi-line info toast (header `Retrying (n/m) in Ns` → countdown ticking, then `HTTP <status> · <kind>` and the provider's clean `.message`; id `gen-retry`, `maxChars: 200`), then a brief `Recovered after N retries` success toast on completion. `_error_reason()` prefers the SDK's `.message` over `str()` for every generation error; `_format_error()` remains the full-detail fallback used in logs. A completely empty completion is surfaced as an error, never retried.
- Meta events (reasoning, reasoning_details) handled via `TRACKED_FIELDS` in `tracked_fields.py`. Each field has a `merge` mode (`append`/`index`) and `stream_to_sse` flag; only `stream_to_sse` fields reach the wire as `meta` events.
- Mid-stream partial saves are wall-clock driven: `_maybe_checkpoint()` writes at most once per `_CHECKPOINT_INTERVAL_SECS` (independent of provider speed and reply length), forced at tool boundaries and on done/error.
- On continue: `prepare_generation_messages()` appends the prefill to API context; for non-echo providers `_run_generation_with_prefill()` synthesizes the existing content as SSE events before real tokens.
- `echoes_prefill` is a per-provider-*type* default (openai_compat=True), not a per-server fact — known sharp edge for endpoints that behave differently than their type suggests.

### Compaction (summaries) — `focus/core/summary.py` (config) + `focus/routers/chats.py` (endpoint)

- `POST /api/chats/{id}/summarize` runs one ephemeral generation (never persisted) and forks a child chat: a `chat_summaries` row (`covered_to_position` = summarized depth) plus `chats.parent_chat_id` / `chats.summary_id` on the child. `db.chats.get_chat_summary_chain` walks the chain oldest-first through the summary owner chats. The endpoint streams SSE and reuses the buffered retry path (`SUMMARY_ATTEMPT_TIMEOUT` per attempt); one in-flight summary per chat (`_active_summaries`, a `chat_id → stop event` map). Cancel via `POST /api/chats/{id}/summarize/stop` — the buffered call is cancelled in flight and the stream ends `done`/`cancelled` (nothing persisted); the composer's stop button drives it (`stopSummary()` in status-panel.js) and launching asks for confirmation first.
- Fork context: `_summary_sections()` (stream_utils) prebuilds four multipart sections — `{{summary}}` (accumulated chunks), `{{summary_pins}}` (user-pinned turns, verbatim), `{{summary_messages}}` (parent's last `keep` turns), `{{summary_media}}` (older media-bearing turns). Preset blocks place them by referencing the macros; a preset that doesn't gets `_default_summary_message` injected adjacent to chat history. `block_type: 'summary'` is an editable sentinel — rendered only for chats carrying a summary.
- **Pins** (`messages.pinned`, manual only): toggled from the message toolbar (`PUT /api/chats/{id}/messages/{id}/pin`, `actionToggleMessagePin`). `{{summary_pins}}` carries pinned turns from the compacted region only (outside the live window, walked across the whole chain), so a pinned setup message survives unlimited compactions. History entries carry the flag as `_pinned`, stripped by the `strip_internal_markers` quirk before the wire (which also drops `_greeting` and the `internal` tool-plumbing flag).
- `summary_config(preset_blocks, settings_json)` is the single resolver (`active`, `instruction`, `keep`, `max_tokens`, `provider_id`); settings live in `presets.settings_json["summary"]` (Summary Settings modal in the prompt arranger). `max_tokens` caps the summary response (0 = provider default; default 8192). Always resolve `active` **with** blocks — a disabled Summary block turns compaction off for the preset.
- Section macros are multipart: `stream_utils.get_prompt_context` pre-seeds each one in the macro dict as `section_token(name)` (`\x00section:<name>\x00`), so `apply_macros` just substitutes the token and `prompt_chain._splice_sections` then replaces it with the prebuilt parts (missing/empty section → token dropped). Tokens must never reach the provider: history text splices them, plain-text fields strip them (`strip_section_tokens`).
- Backup/export carries the lineage: `chat_summaries` travels in the archive, export closes over `parent_chat_id` ancestry + summary chains (`exchange._chat_lineage_ids`), and `chats.summary_id`/`parent_chat_id` are remapped as FKs (`POLYMORPHIC_FK_COLUMNS`) — a restored fork keeps its chain and parent window.

### Tool system

- Data model: `ToolSpec`, `ToolParam`, `ToolCall`, `ToolResult` in `tools/__init__.py`
- Builtin: `read_file`, `list_dir`, `read_image`, `execute_shell`. Each has a `writes` flag for read-only filtering.
- External: JSON configs in `tools/` (recursive scan, 2 levels, skip hidden dirs). Format: `ExternalToolConfig(name, description, command, timeout, writes, params)`.
- Iteration: `_run_generation()` loops up to the chat's `max_tool_iterations` (default 25; `0` = unlimited; otherwise clamped 1–100; set in the tools modal). Per iteration: stream → detect `tool_calls` → break → execute → emit results → loop. Hitting a finite cap still emits `done` so the variant is finalized.

### Provider system

- Each LLM provider = a module in `providers/` implementing the base interface. `stream_complete(messages, stream=True, **kwargs)` always yields the same event stream; `stream` selects the *upstream API mode* — `provider.stream_complete(..., stream=False)` must make one complete call (`chat.completions.create(stream=False)` / `generate_content`) and replay it as `token`/`meta`/`tool_calls`/`usage`/`done`. `openai_compat` branches inline; `google_base` dispatches `_do_stream` vs `_do_generate`. `to_provider_tools()` converts ToolSpec → OpenAI-compatible format.
- Frontend: single shared `provider-form` with `prov-form-*` id prefix. Flow: `resetProviderForm()` → `populateProviderForm(data)` → `extractData(form)` for PATCH/POST.
- **Saved keys**: the `secrets` table is a reusable library. The provider form stores an ordered list of refs (`SECRET:<name>`) or raw values in `config.api_keys`, and `config.active_key` names the one in use (`db.providers.provider_key_refs` / `active_key_ref`, switched by `POST /api/providers/{id}/active-key`); the legacy `api_key` column is only a one-element fallback when `config.api_keys` is absent. The library is its own banded modal (`GET /partials/secrets?pick=1`, server-rendered in `partials/modals/secrets.html`, `secretsList` surface in `refresh.js`) — `pick` makes rows append a reference to the form's list. Adding a key is a separate stacked form (`modal-secret-new`): named it is saved to the library (and referenced in pick mode), unnamed in pick mode it is inlined as a one-off raw key. Values never leave the server: the list carries a masked preview only.
- Option pickers (OpenRouter route/quant, character theme, ...): **one shared searchable picker** — `partials/modals/option-picker.html` (included last in `chat.html`; always in DOM, stacks above all modals) + `static/js/ui/option-picker.js` exposing `openOptionPicker(options, title, cb)`. Values land in hidden inputs + display spans.
- **Request pipeline**: `focus/providers/quirks.py` owns the ordered `QUIRKS` table (predicate + transform) run by `apply_request_quirks()` before each call. Adding a quirk = one function + one entry; never an `if type ==` ladder in the generation flow. Wire-format assembly stays in the adapter. `stream_utils.prepare_generation_messages` is a thin delegator. Pure transforms live in `focus/core/request_transforms.py` (provider-agnostic, no cycles).
- **Capabilities & registry**: each adapter declares `type` + `profile` (`focus/providers/profile.py`); `BaseProvider.__init_subclass__` self-registers in `registry.py` and copies `supports_tools`/`supports_prefill`/`echoes_prefill` from `profile.caps`. `create_provider` is a registry lookup + `from_row()` — no type ladder.
- **Frontend schema**: `focus/providers/schema.py::provider_schema()` (defaults, effort options, forward/visible fields, capabilities, form config, labels, ordered type options) is embedded as `window.PROVIDER_SCHEMA` and consumed by `static/js/core/provider-schema.js` (`ProviderSchema.*`). The sampler-modal getters, `sampler-defaults.js`, `providers.js` form visibility, provider-type `<option>` lists, continue-button visibility, and the Claude-cache predicate all read from it. Add per-type UI facts there instead of new JS conditionals.
- **Client records**: `static/js/core/provider-store.js` (`ProviderStore`) is the client SSOT for provider records — seeded once in `chat.html`, refreshed after every provider CRUD (`providers.js` save; the modal delete `hx-on`). The status panel, sampler and the Claude-cache check read the active provider from it; never reintroduce a page-load `APP_PROVIDERS` snapshot (a provider created after load must be visible without a reload). Selection ids stay in `StateManager`; the store owns only the data.
- Cross-provider shared payloads live in a shared module (e.g. `google_safety.py`) and are delivered through the relevant adapter — so a provider's wire format can be reused by another route (Gemini safety settings through OpenRouter) without importing the other SDK.

### Theme system

- Themes live in the `themes` table (built-ins seeded as `is_system` rows with fixed ids `builtin-*`; custom themes CRUD via `/api/themes`). Built-ins are editable in place; `POST /api/themes/{id}/reset` restores their canonical seed values; only custom themes can be deleted. A palette change ships through `migrate_builtin_themes`, which repaints a row only while it still matches the old canonical seed (edited built-ins are left alone) and drops retired built-in ids with their slot/character references. `--text-faint` is themeable (seeded; falls back to a `text-muted`/`surface` mix) and `--text-on-accent` is derived from accent luminance in both `theme-manager.js` and `base.html`'s pre-paint; `--text-on-scrim` stays fixed white over dark scrims.
- **Pair model**: two global slots — `dark_theme_id` + `light_theme_id` in settings, written via `PUT /api/settings/theme {slot: 'dark'|'light', theme_id}`. The app always follows `prefers-color-scheme`; effective = `characters.theme_id ?? (dark ? dark slot : light slot)`. Want "always dark"? Set both slots to the same theme.
- `chat_page` embeds `window.THEMES` + `window.THEME_STATE` server-side; `theme-manager.js` applies, caches both slot palettes to `focus-theme-state` (flash-free pre-paint in `base.html`), re-resolves on `matchMedia` change, `character-changed`, and `character-edited` events. Action feedback via the toast system (`showToast` in `notifications.js`, container `#toast-container` in `base.html`).
- Theme modal (`partials/modals/theme.html`): clicking a row selects it for editing; per-row Dark/Light `.chip`s assign the slots (mutually exclusive, `.chip.active`); "New" creates the theme immediately from the typed name + current picker colors (toast, stays open, new theme selected). Live picker preview is NOT saved: `dirty` state (name/pickers vs stored values) enables Save, shows an "Unsaved changes" hint, and prompts before switching themes (`switchTo` + `openConfirmModal`).

### CSS layer — `static/css/`

- Import order in `static/tailwind-input.css` is load-bearing: `tailwindcss → variables (tokens, material, ink/tint) → tokens (@theme) → base → animations → surfaces/* (shell · sidebar · messages · forms · modals) → primitives`. Primitives come last so they win every collision. Surfaces may set **layout** on their own containers; they may not restyle a primitive — `tests/frontend/test_css_ownership.py` enforces it (no look property on a primitive's selector outside `primitives.css`, no `:not(` anywhere).
- `primitives.css` is the closed vocabulary: controls `.btn .key .nav .link .chip .tab .pager`, inputs `.field .check .switch`, structure `.rail .row .well .frame .panel .card .divider .disclosure .grip`, feedback `.toast .tooltip .spinner .empty .note .tag .avatar`. Intents `.primary .create .danger`; sizes `.sm .lg .xl`; state classes as JS toggles them.
- **Type rules** (quiet-ification pass): engraved type (mono, caps, tracked) is rationed to section headers and modal titles only — buttons, fields, and row values stay quiet sans (UI labels) or lowercase mono (data). Fills mark touchable things (`--ink-1` tiles/controls); sections and rows stay flat with hairline dividers *between* rows, never frames *around* them.
- **New UI checklist:** compose the primitives (`.btn`, `.card`, `.field`, `.sidebar-section`, …) and the layer cascades for free; a genuinely new structural class needs one block in `primitives.css`, plus its geometry in the owning surface. Composed shapes already have macros — `row_label`, `toggle_row`, `slider_row`, `reload_key`, `search_toolbar`, `modal_footer`, `tab_bar`, `role_select` — so a settings line or a picker is never hand-authored. Full geometry, chassis anatomy and the layout traps live in `UI.md`.

### Fonts

- Both families are self-hosted woff2 under `static/fonts/`, declared in `static/fonts.css` (linked from `base.html`), not downloaded by `vendor-sync.py`. `--font-sans` = **Ronzino** (static; 400/500/700 + obliques — **no 600, so `font-semibold` renders as 700**), `--font-mono-ui` = **Necto Mono** (single 400 weight). Both SIL OFL 1.1, © Collletttivo; license texts live next to the fonts and are listed in `NOTICE`. Replacing a face means adding an `@font-face` here and updating `--font-sans`/`--font-mono-ui` in `tokens.css` / `variables.css`.

### Macros (`focus/core/macros.py`)

- Built-in macros: `build_base_macros()` (values) and `MACRO_DEFINITIONS` (metadata). Must stay in sync — test `TestMacroDefinitions::test_keys_match_build_base_macros` enforces this.
- Special tokens: `{{getvar::key}}`, `{{setvar::key::value}}`, `{{var::key::value}}`, `{{trim}}`, `{{// comment}}`, `{{media:id}}`, plus CBS `{{random:}}`/`{{pick:}}`/`{{roll:}}`/`{{reverse:}}` and the compaction macros below
- Comments `{{// ...}}` stripped pre-resolution, depth-aware for nesting.
- Template globals `macro_definitions`/`special_tokens` registered in `pages.py`.

### Regex scripts (`focus/core/regex_scripts.py`)

- Server-side, **Python-only** find/replace. Never a JS engine: both the prompt path and the display path compile with Python `re`. JS is UI glue only (the Advanced modal's Regex tab).
- **Two application points:** prompt assembly (`prompt_chain.assemble_prompt` takes `regex_scripts` and applies them to macro-resolved `cleaned_history` *before* in-chat block injection, so depth counts real turns) and display render (`pages._apply_display_regex`, after `_resolve_macros_for_display`). UI rendering applies them server-side; stored content is never mutated.
- **Output targets:** `apply_prompt` (rewrite the text sent to the model), `apply_display` (rewrite the rendered chat), and `as_block` (turn the display match into a collapsible block — forces `apply_display` on, its Replace only affects the prompt side). There is deliberately no persistent/bake mode.
- **Scope/order:** `global` scripts run first, then the chat preset's; resolved by `focus/db/regex_scripts.py::resolve_for_chat`. Within a scope, order is drag-controlled (SortableJS `handle: '.regex-handle'`, like the arranger). Cross-scope drags are disabled.
- **Depth window:** `min_depth`/`max_depth` count from the newest real message (0 = newest, `-1` = unlimited); synthetic tool/internal turns are skipped by `_real_depths`.
- **Timeout:** each text runs via `asyncio.to_thread` + `wait_for(REGEX_TIMEOUT=3s)`; on timeout the original text wins. `MAX_INPUT_LENGTH` caps input — including the Test box (`POST /api/regex-scripts/preview`), which gets the same thread+timeout treatment so a pathological pattern can't hang the event loop.
- Storage is the `regex_scripts` table; `scope_id` is polymorphic (a preset id) and listed in `exchange_remap.POLYMORPHIC_FK_COLUMNS` so backup/export remaps it. Global scripts always travel; preset scripts only when their preset is exported.
- UI: Regex tab is a server-rendered list (`GET /partials/regex-scripts?preset_id=`), CRUD at `/api/regex-scripts`, preview at `POST /api/regex-scripts/preview` — the "Test" box calls the server because Python is the regex authority (a JS preview would lie).

### Structured responses (`focus/core/structured.py`)

- JSON-schema-constrained completions: the active row's schema goes upstream as OpenAI-style `response_format` (`json_schema`); the model's JSON reply (repaired with `json_repair` when truncated) is rendered through a Handlebars template (pybars3) into the stored message text.
- Scoped exactly like regex scripts — `global`/`preset` rows in `structured_responses`, one *enabled* row per scope (a preset row overrides the global one), CRUD at `/api/structured-responses`, list partial `/partials/structured-responses`; `scope_id` travels in `POLYMORPHIC_FK_COLUMNS`.
- **Always buffered:** an active response forces `stream_enabled=False` in `stream()` (raw JSON must never stream or checkpoint) and one `token` replays the finished render before `done`. A render failure aborts and rolls the assistant slot back (`_abort_structured`); a user stop before the first token finalizes as a normal stop (empty accumulator skips the render). Continue disables structured for that variant; tools are disabled while structured is active (logged).
- Resolution happens at generation time (`stream_utils._resolve_structured`): schema macros resolve there (malformed schema → 400 before the stream starts). Templates resolve at compile time via `macros.resolve_template_macros`, which substitutes only recognised macros and leaves every other `{{...}}` (Handlebars paths, block helpers, the `macro` helper) untouched — triple braces insert raw, double braces HTML-escape. `validate_template` runs the same pass with empty macros so macro-bearing templates pass the save-time guard; anything that only fails at render aborts the whole generation, so keep templates render-safe.
- **Provider mapping:** the openai-compat family passes `response_format` through natively; `google_base.stream_complete` maps it onto Gemini's `response_mime_type: application/json` + `response_json_schema`.
- **Templates are compile-guarded:** `_compile` (lru_cache — one compile per template text, bounds pybars' per-compile `sys.modules` registration) rejects bracket paths (`{{[...]}}`) at every entry point because pybars splices them into generated source verbatim (code execution); string literals and literal text stay allowed. `{{ }}` HTML-escapes, `{{{ }}}` is raw — the shipped default template is `{{{text}}}`.

### Action palette — button intent

Colour follows the **verb on the label**, not the feature. One green create per surface; everything else stays in the indigo/neutral/red lanes.

| Verb | Class | Examples |
|---|---|---|
| **Create** — a new entity comes into existence | `.btn.create` (green) | New, Add, Create, Duplicate, Start Chat |
| **Commit** — persist/confirm changes to something that already exists | `.btn.primary` (indigo) | Save, Apply, Done, Confirm, Rename, Select, Export |
| Navigate / dismiss | `.btn` / `.link` | Back, Close, Cancel, Editor |
| **Destroy** | `.btn.danger` (red) | Delete, Remove |
| **Flag** (user metadata) | `.fav-star.favorite-active` (amber) | Favorite, pinned message |

- **Litmus test:** after the click, is there one more row/entity than before? → green. Otherwise → indigo. A form submit that creates a resource takes the create colour ("Add Provider"); one that persists edits takes indigo ("Save").
- **Save is never green.** "Save"/"Save Changes" mutate the thing you're editing — commit, so indigo. If a button really only adds a row, its label should say so ("Add") and *then* it can be green; never leave a green "Save".
- `.create` is tinted at rest and deepens on hover — never a solid block (`--success-tint*` / `--success-edge`).
- The intents compose with every shape: `.btn .key .nav .chip .link .tab .row .well .note` all take `.primary` / `.create` / `.danger`. Use the modifier, never a bespoke class.
- Colour lives in `primitives.css` only; a surface that repaints a control gets overridden (see the ownership test above).
- `--success` is otherwise used only by toasts and the ticker's reasoning phase, so the green channel is free. `--role-user` is a near-green — don't place a create button directly against a user-role chip.
- **Import is neutral, not create** — it's a file ingest; a second green next to Create dilutes the cue.
- **Opening a picker is navigation, not create** — e.g. "Add Character" in the right pane opens the character modal, so it stays indigo. The label says Add; the behaviour selects.

## Common gotchas

- **Scripts in htmx-swapped partials**: a `<script>` inside a partial executes on every swap. Moving it to the host page (e.g. `chat.html`) makes its top-level init run **once at page load** — before the swapped content exists. Replace swap-time init (`setTimeout`, querying freshly-rendered nodes) with an `htmx:afterSwap` hook keyed on the target id (`providers.js` → `#providers-modal-body-inner` is the reference case; `test-providers-modal-init.js` guards it).

- **`x-show` needs `x-cloak`** — Alpine loads `defer`, so overlays using `x-show` without `x-cloak` flash visible during HTML parsing.
- **`:last-of-type` isn't "last with this class"** — the scroll sentinel shares the same tag. Use `querySelectorAll('.message')` and take the last NodeList element.
- **Never htmx-swap `#message-list`** — the list is rendered by `refreshMessageList()`, which reconciles in place and calls `pruneMessages()` itself. `message-pruner.js` replaces off-screen messages with placeholders; check `window._isMessagePruned(id)` (or resolve through `MessageIdentity.placeholder`) before DOM ops. The streaming message is excluded. Culling stays on in delete mode: selection is an id set (`delete-mode.js` `selectedIds`), and `applyDeleteModeToNode(msg)` re-applies checkbox visibility/checked state when a row scrolls back in.
