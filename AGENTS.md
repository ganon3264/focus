# Focus

Single-user local chat front end for LLM characters. FastAPI (async) + aiosqlite,
Jinja2, HTMX 2 + Alpine 3, Tailwind v4, uv + hatchling. Python tests are pytest;
JS tests are plain Node scripts.

Companions — read the one that owns the area instead of re-deriving it here:

- `UI.md` — CSS layers, modal chassis and bands, geometry numbers, layout traps. If
  it disagrees with this file, it is right.
- `TOOLS.md` — external tool JSON schema and the script stdin/stdout contract.
- `EXTENSIONS.md` — extension schema, triggers, result contract.

## Run and test

    ./start.sh                          # vendor sync -> tailwind build -> uv run main.py
    ./test.sh                           # uv sync --locked --group dev, then pytest + coverage
    ./test.sh --no-cov
    node tests/frontend/test-x.js       # one JS test; helpers.js has the DOM mocks

`static/tailwind.css` is generated and gitignored — rebuild after any CSS or template
change. `tests/frontend/grid-audit.js` is Playwright against a running server, so it
is not part of `./test.sh`.

## Tests

Assert the outcome, never the implementation. A test that fails when a helper is
renamed, a file moves, a class is reordered or a data table is edited — while the
behaviour is identical — is worse than no test: it taxes every refactor and catches
no regression. Split by subject: `tests/api/` drives the app over HTTP and reads DB
state, `tests/units/` calls the public entry point, `tests/frontend/` evals the
module and reads the DOM or requests it produces.

Banned shapes, all of which had to be removed once: mirror tests (a hand-copied
production table/constant/path list asserted back against production),
`_private_helper(...)` as the subject when a public path reaches the same outcome,
`typeof fn === 'function'` smoke, spies on stubs, `class="a b c"` and
`style="display: …"` substring asserts (parse the node — `tests/helpers.py::parse_html`
in Python, the mock DOM in JS — or address `data-ui` hooks), source-file position
and `py_compile` checks, and
log/toast/error copy — assert the record, the event or the toast fired, not its
wording. A test-local copy of an upstream API payload pins what we do not control
and proves nothing; map the incoming shape and assert our output. The one allowed
copy is a fixture-sync test where one side is generated.

## Layout

    main.py             app entry; serves /assets (check_dir=False) and /static
    focus/core/         database, models, macros, media, message_render, paths,
                        card_parser, segments, tracked_fields, prefs, retry,
                        progress_stream, request_transforms, regex_scripts,
                        structured, summary, search, usage_stats, utils
    focus/db/           CRUD per domain, _core, settings, prefs, cleanup
    focus/providers/    base, registry, profile, quirks, schema, config, the adapters,
                        google_base/aistudio/vertex, google_safety
    focus/routers/      pages, chats, stream + stream_utils, presets, providers,
                        settings, themes, tools, extensions, backup, exchange,
                        regex_scripts, structured_responses, characters, personas
    focus/tools/        builtin, external, executor, provider_adapter
    focus/extensions/   loader, runner, triggers
    focus/              crud.py, exchange.py, exchange_remap.py, exchange_sanitize.py,
                        prompt_chain.py, backup.py
    templates/          full pages
    partials/           HTMX fragments
    static/css/         variables, tokens, base, animations, surfaces/*, primitives
    static/js/          core/ messages/ modals/ ui/ features/ utils/
    static/fonts/ static/vendor/            self-hosted faces; vendor libs
    assets/             attachments, characters, personas, blocks, presets,
                        compressed, tool
    data/               focus.db, backups/
    tools/              external tool configs (EXTERNAL_TOOLS_DIR, scan depth <= 2)
    tests/              api/ units/ frontend/ e2e/

## Frontend core

State — `core/state-manager.js` owns `character_id`, `persona_id`, `preset_id`,
`provider_id`, `provider_type`. Setters `.setCharacter/.setPersona/.setPreset/
.setProvider(id, type)`, all accepting null. Ids persist onto the chat row, except a
no-op when there is no chat (the chatless greeter) and the provider, which persists
to settings via `PUT /api/settings/active-provider`. `getAll()` returns those five
keys only; `chat_id` and `multimodal_enabled` need `.get()`. `.on(event, fn)` gets
`{prev, value}` for entities and `{prevId, prevType, id, type}` for the provider.

Live updates — `core/refresh.js` maps resources to surfaces, so a mutation site
declares what it wrote and nobody hand-wires reloads. `Refresh.changed(...resources)`
coalesces within a tick, drops surfaces already `covers`-ed by a loader, runs the
rest; `Refresh.mutate(url, opts, {changed})` writes through `hxFetch` and invalidates
only on `res.ok`; `Refresh.load(surface)` forces one. A surface is
`{deps, load, guard?, when?, covers?}` — `guard: 'not-streaming'` is applied
centrally (never re-check `Generation.isActive()` per feature), `when` gates the
flush. Also exports `flush()`, `surfaces`, `resources`. Never call `changed()` from a
loader. In-place list editors (regex/structured rows, tool and extension toggles)
update their own row instead, so a field blur does not flash the whole list; backup
restore and import replace arbitrary entities and hard-reload.

Actions — `core/actions.js` delegates `data-action="fnName"` (globals and dotted
paths like `Foo.bar`) over click/submit/change/input. A `data-action` on a `<form>`
fires for submit only, so the form's action is its submit handler. Message toolbar
buttons read their context from `closest('.message')` data attributes.

Modals — `ui/modal.js` owns the lifecycle as `ModalController`
(`open/close/closeTop/isOpen/isDirty/setDirty/refresh/onOpen`; `openModal`/
`closeModal` are wrappers) over the `modal_shell` macro. Show and hide toggle the
`hidden` class, never `style.display`. z-index: `--z-modal` 50 → `--z-modal-sub` 100
→ `--z-overlay` 10000 → `--z-max` 10010, and a shell stacking over its opener passes
an explicit `z_index`. Dirty tracking is opt-in through
`modal_shell(dirty_fields=…, dirty_label=…)` — a new field is not dirty unless its id
is listed — and save handlers close with `closeModal(id, {discard: true})`.

Preferences — `focus/core/prefs.py` is the closed set (`DEFAULTS`, `CHOICES`,
`normalize`), `focus/db/prefs.py` stores it as one JSON blob; `GET/PUT
/api/settings/prefs`, `DELETE` restores defaults. `window.PREFS` is embedded in the
page and `core/prefs.js` loads from `base.html`'s head before paint. `Prefs.get/set/
reset()` is the only client API: `set` applies optimistically, adopts the server's
normalized answer, rolls back and toasts on failure, and fires `prefs-changed` once
per settled key. The tab is server-rendered (`data-pref` + `actionSetPref`), has no
Save verb, and one Restore Defaults in the foot. A new preference needs a default in
`DEFAULTS` plus a row — never a reset branch or a per-row sync. Everything here is
display or input only: anything that changes what reaches a provider belongs to the
preset or the chat.

Toasts — `ui/notifications.js` over `#toast-container` in `base.html`.
`showToast(msg, {type, duration|id, maxChars})` plus `showInfoToast`,
`showSuccessToast`, `showErrorToast` (persists, Copy/Close), `showImportToast`,
`hideToast(id)`, `hideErrorToast`, `hideInfoToast`, `hideAllToasts`. Dedup by id or
type+message, five visible max, never block with `alert()`.

SSE — `core/sse.js::readEventStream(response, onPayload)` is the only read loop
(return `true` to stop and cancel); `streamProgress(url, opts, onEvent)` interprets
`progress | done | error` for maintenance work, which shows one id-keyed live toast.
Server side is `focus/core/progress_stream.py::progress_stream(run)`; the work
function takes `async progress(label, current=0, total=0)`.

## Messages

Identity — `messages/message-identity.js` translates between the bare id and its two
derived forms: node `#message-<id>` via `domId()`/`node()`, pruned stub
`.message-placeholder[data-msg-id]` via `placeholder()`. The pruner's `_pruned` map is
keyed by bare id and `_forgetPruned(id)` drops a stale entry. Nothing writes either
form by hand.

The list — `message-refresh.js::refreshMessageList(chatId, changedIds)` fetches the
server partial and reconciles in place (reuse / reorder / insert / drop), keeping
scroll, open reasoning and pruned stubs; `refreshMessagesAfterStream` and
`refreshChatMessages` delegate to it and `refreshSingleMessage` is the cheap one-node
path. `post-process.js::processMessageList(container)` is the single post-render pass
(markdown, reasoning buttons, timestamps, delete-mode chrome, send/continue state,
`ChatScroll.init()`). Fetch partials with `hxFetch` so they share the write queue.
Never htmx-swap `#message-list`.

Segments — a message is `text | reasoning | tool_boundary` (`segments_json`). Message
chrome has one markup source: the macros in `templates/macros.html`, rendered into
inert `<template>`s by `partials/chat/message-templates.html`; the JS builders only
clone and fill, and `tests/frontend/fixtures/message-templates.html` is kept in sync
by `test_message_template.py`. Use `preserveOpenStates()` for in-place re-renders;
fresh server nodes start folded by design.

Scroll — `ui/scroll-manager.js` is the only writer, exposed as `ChatScroll`. It
measures one thing (`distance()` from the scroller's bottom, 1px of subpixel slack)
and does one thing (`pin()`), so the steady state is pinned. Growth is the only
signal: a `ResizeObserver` on `#message-list` calls `onGrowth()`, so no SSE handler
scrolls — every token render, unfolded block, tool card, decoded image and
re-inflated stub resizes the list. `follows()` is the one predicate for "may growth
move the view" (mode `always` / `pinned` at the bottom / `disabled`), and every pin
site asks it; `unpin()` is the reader's side, called from a synchronous `scroll`
listener and when an older reasoning block is unfolded. The first observer callback
is the landing scroll; it stands down when `?at=` names a search hit.
`init()` is idempotent and re-arms on a replaced list node. (`ui/chat-controls.js`
also calls `scrollIntoView` once on a fresh skeleton — the only other writer.) The
mode comes from the `follow_stream` preference.

Reasoning blocks — `messages/reasoning-utils.js::setReasoningOpen(msg, open)` is the
one writer of the first (headless) block's state: message class `reasoning-open` plus
`hidden` on the body. The `reasoning_open` preference gates it:
`reasoningOpensOnStream()` opens the live block once, when it appears (later blocks
are `details` with their own toggle), `reasoningStaysOpen()` makes the post-stream
refresh re-open the server node, which is server-rendered folded.

Streaming client — `core/generation-session.js` owns the lifecycle: AbortController,
active flag, streaming id, the SSE read loop and the stop ladder. API
`Generation.begin(chatId, asstDiv, opts)`, `.stop()`, `.cancel()` (silent, used when
the provider changes), `.isActive()`, `.streamingId()`. Stop POSTs
`/api/stop-generation/{id}` with a 4s timeout and waits for the normal `done`; if the
POST fails or nothing arrives in 8s it hard-aborts, which is safe because Starlette
cancels the generator and the server persists the partial. A 404 from the stop
endpoint means the run already finished. `messages/stream-events.js` holds
`StreamState` per run and the `HANDLERS` table behind `dispatchStreamEvent()`;
handlers record outcomes on the state object and never throw. Token renders are
rAF-coalesced and, past 4KB, throttled (`renderInterval()`).
`finalizeStreamRender()` force-flushes before the post-stream refresh and calls
`syncStreamingView` on the way out — a buffered reply's `token` and `done` land in
one tick, so its body would otherwise never be shown. `generation-ui.js` owns the
send/stop buttons and `clearStaleContent()`; the pending rail is markup-side
(`showMessagePending`/`hideMessagePending`), and the ticker's phase changes
`--tick-color` and `--tick-rate` (applied as `playbackRate` via `applyTickRate`).

## Chat surfaces

Search is a modal, not a field in the right pane (`features/chat-search.js`, ids
`#chat-search-field`, `#chat-search-scope`, `#chat-search-lane`,
`[data-ui="search-readout"]`; 180 ms debounce). Matching is FTS5, not substring:
`message_fts` (porter + unicode61, `variant_id` UNINDEXED) is fed by triggers on
`message_variants`, so every writer — checkpoints, edits, import — keeps it current
without knowing it exists; only the update and delete triggers delete by
`variant_id`, because that scan is the whole table and an import would go quadratic.
`core/search.py::match_query()` turns the box into quoted prefix tokens ANDed
together and `crud.search_messages` ranks with `bm25` (best first, 40 max, active
variant, live chats only). The snippet is FTS5's own, so highlights survive stemming;
it arrives with `\x02`/`\x03` markers that `render_snippet()` escapes and turns into
`<mark>`. `init_db` backfills a pre-trigger database. A hit links to
`/chat/{id}?at={message_id}` and that query parameter owns the landing position.

Usage readouts — `core/usage_stats.py` has two shapes: `summarize_usage(rows)` for one
message (a bubble is several provider calls, one per tool round, so the figures sum
and the per-call rows are a disclosure) and `summarize_lifetime(rows)` grouped per
provider/model for the System modal's Usage tab. Both are read-only, tallies of what
the database still holds, and `cost` only covers providers that report it.

Custom character blocks are prompt-side only (a preset `char_blocks` sentinel splices
them), so editing one does not invalidate the message list. The list is server-rendered
(`GET /partials/char-blocks/{char_id}`, one row from
`GET /partials/char-block/{char_id}/{block_id}`, order via
`POST /api/characters/{char_id}/blocks/reorder`) and every edit saves immediately —
there is no Save verb. Wire Sortable and the count from `htmx:afterSwap`, and scope
the count to `#modal-edit-character`, since the same `data-ui` hook exists on the
editor door.

First launch — the chatless greeter is the setup checklist until an active provider, a
preset and a character exist, then the welcome pane. Only those three are rows (the
`data-setup-step` values), the persona is a note under the CTA, and nothing matches on
copy. It is a Refresh surface, OOB-swapped on every resource change, so a create must
declare what it created or the guide keeps claiming the step is unstarted.

Shared option picker — `ui/option-picker.js` `openOptionPicker(options, title, cb)`, one
searchable list reused by OpenRouter route/quant, character theme and friends; the
value lands in a hidden input plus a display span.

## Generation server side

`/api/stream` always answers `text/event-stream`, and every payload is
`{"type": …}`: `start | token | meta | retry | tool_calls | tool_result | extension |
debug | done | error`. Reasoning rides `meta` with `field: "reasoning"`. `usage` and
`superseded` stay internal to `_run_generation`/`_handle_event`; a superseded run
closes silently. `done` carries `finish_reason` when the provider gave one,
canonicalised by `_finish_reason()` (OpenAI `length` and Gemini `MAX_TOKENS` both
become `length`, which the client turns into one info toast). Dispatch is
`HANDLERS[type]`; unknown types log a warning.

- `_active_generations` maps `message_id → _ActiveGeneration` (`chat_id`,
  `provider_id`, stop event, `superseded`). Registering a generation supersedes any
  other in the same chat; editing or deleting a provider stops its runs
  (`stop_generations_for_provider`).
- Buffered mode is not a separate response: with the sampler's `stream_enabled` off,
  `_run_generation` makes a non-streaming provider call and replays the finished text
  as one `token` before `done`, so retry and error feedback still reach the client
  while no partial content is ever shown.
- Auto-retry (`focus/core/retry.py`): failures before the first token are retried with
  backoff and `Retry-After`, per tool iteration; after any token the failure is
  surfaced instead. Config lives in the provider's `config_json["retry"]`; defaults
  are 5 retries, 2s base, 20s max delay, 120s hard cap per delay and a 180s budget per
  generation, and 429s are retried only with `on_rate_limit` (default off). Each
  attempt emits a `retry` event (`attempt`, `max`, `delay`, `kind`, `status`,
  `reason`) rendered as one live `gen-retry` toast. An empty completion is an error,
  never a retry. `_error_reason()` prefers the SDK's `.message`.
- Checkpoints: `_maybe_checkpoint()` writes at most once per
  `_CHECKPOINT_INTERVAL_SECS` (wall clock, independent of reply speed) and is forced
  at tool boundaries; `done`/`error` run the final save, and a disconnect persists via
  `_finalize_detached` (shielded cancel scope, own connection).
- Tools: `_run_generation` loops up to the chat's `max_tool_iterations` (default 25,
  `0` = unlimited, else clamped 1–100). Stream → detect `tool_calls` → execute → emit
  `tool_result` → loop. Hitting a finite cap still emits `done`. Builtins live in
  `focus/tools/builtin.py` (`read_file`, `list_dir`, `read_image`, `execute_shell`,
  each with a `writes` flag for read-only filtering); external tools are JSON configs
  under `tools/` (`ExternalToolConfig`, see `TOOLS.md`), and both carry a `category`
  and a `multimodal` flag. Extensions (`focus/extensions/`, see `EXTENSIONS.md`) run
  through the same executor path and report back as `extension` events.
- Continue: `prepare_generation_messages()` appends the prefill to the API context and
  `_run_generation_with_prefill()` synthesizes the existing text as events for
  providers that do not echo it, so the stream always carries the full text and the
  client never seeds content (it binds the existing `.message-content` as the first
  segment). `echoes_prefill` is a per-type default, not a per-server fact.
- Meta fields go through `focus/core/tracked_fields.py::TRACKED_FIELDS`; each has a
  `merge` mode (`append`/`index`) and `stream_to_sse`, and only the flagged ones reach
  the wire.

## Prompt pipeline

`focus/prompt_chain.py::assemble_prompt` builds the preset's blocks, applies macros,
runs prompt-side regex scripts on the resolved history before in-chat block injection
(so depth counts real turns), splices the compaction sections, then splices
`{{media:…}}`. Wire-format quirks are applied after that, in `providers/quirks.py`.

Macros — `focus/core/macros.py`: `build_base_macros()` and `MACRO_DEFINITIONS` must
stay in sync (`test_keys_match_build_base_macros`). `apply_macros` is a
document-order walk over one pass, repeated up to `MACRO_MAX_PASSES` for chained
output: setvars apply where they appear, an `{{if}}` is decided with the values in
force at that point, and only the winning branch is evaluated. ST block syntax is
supported as found in the wild (`{{setvar k}}…{{/setvar}}`, `{{if}}…{{else}}…{{/if}}`,
`{{#if}}` preserves whitespace); falsy is ST's five strings exactly (`""`, `false`,
`0`, `off`, `no`), never Python truthiness. `{{pick}}`/`{{roll}}` seed from the
internal `_chat_id` macro. Macros 2.0 operators are unsupported on purpose, and
`resolve_template_macros` owns `{{#if}}` for structured templates — keep it away from
the conditional walker. Section macros for compaction are pre-seeded as
`\x00section:<name>\x00` tokens (`section_token()`), spliced by `_splice_sections`,
and stripped from plain-text fields (`strip_section_tokens`) — they must never reach
a provider.

Regex — `focus/core/regex_scripts.py`, Python only on both sides: prompt assembly and
display render (`pages._apply_display_regex`, after macro resolution). Stored content
is never mutated. Targets are `apply_prompt`, `apply_display` and `as_block` (which
forces display and renders the match as a collapsible block); there is deliberately
no bake mode. Order: global scripts, then the preset's, resolved by
`resolve_for_chat`, drag-ordered within a scope. `min_depth`/`max_depth` count from
the newest real message (`-1` unlimited) and skip synthetic turns; `placement` gates
which segment a script applies to. Each text runs in a thread under
`REGEX_TIMEOUT` (`MAX_INPUT_LENGTH` caps the input, including the Test box, which
calls `POST /api/regex-scripts/preview` because a JS preview would lie).
`scope_id` is polymorphic and listed in `exchange_remap.POLYMORPHIC_FK_COLUMNS`.

Structured responses — `focus/core/structured.py`. The active row's schema goes
upstream as `response_format: json_schema` (Gemini gets `response_mime_type` +
`response_json_schema`), the JSON reply is repaired with `json_repair` and rendered
through a pybars Handlebars template into the stored text. One enabled row per scope,
a preset row overriding the global one. Always buffered:
`_run_generation` forces `use_stream = False` and replays the render as one token; a
render failure rolls the assistant slot back (`_abort_structured`), continue disables
structured, and tools are disabled while it is active. Templates are compile-guarded:
`_compile` is lru-cached and rejects bracket paths (`{{[…]}}`, code execution), and
`validate_template` must be able to run a template with empty macros so save-time
guards match render time. Routes: CRUD at `/api/structured-responses`, list partial
`/partials/structured-responses`, `POST /api/structured-responses/preview`.

Compaction — `focus/core/summary.py` + `focus/routers/chats.py`.
`summary_config(preset_blocks, settings)` is the single resolver (`active`,
`instruction`, `keep`, `max_tokens`, `provider_id`), settings under
`presets.settings_json["summary"]`; resolve `active` with the blocks, since a disabled
Summary block turns compaction off. `POST /api/chats/{id}/summarize` runs one
ephemeral generation and forks a child chat (`chat_summaries.covered_to_position`,
`chats.parent_chat_id`/`summary_id`); `GET`/`PUT` read and edit the chunks, cancel is
`POST …/summarize/stop`, one run per chat. Sections: `{{summary}}`,
`{{summary_pins}}` (pinned turns verbatim), `{{summary_messages}}` (last `keep`
turns), `{{summary_media}}`; a preset with no summary block gets
`_default_summary_message` injected next to chat history. Pins are manual
(`PUT /api/chats/{id}/messages/{id}/pin`) and travel as `_pinned`, stripped before the
wire along with `_greeting` and the `internal` tool flag. Export carries the lineage.

## Providers

An adapter subclasses `BaseProvider`, declares `type` and `profile`, and
self-registers through `__init_subclass__`; `create_provider` is a registry lookup
plus `from_row()`. `stream_complete(self, messages, **kwargs)` always yields the same
event stream, with `stream` as a kwarg selecting the upstream mode — `stream=False`
means one complete call replayed as `token`/`meta`/`tool_calls`/`usage`/`done`
(`openai_compat` branches inline, `google_base` dispatches `_do_stream` vs
`_do_generate`). `to_provider_tools()` converts `ToolSpec` to the OpenAI shape.

Request pipeline — `providers/quirks.py` owns the ordered `QUIRKS` table (predicate +
transform) run by `apply_request_quirks()` before each call. Adding a quirk is one
function plus one entry, never an `if type ==` ladder; pure transforms live in
`focus/core/request_transforms.py`. `stream_utils.prepare_generation_messages` delegates.
Caching: `supports_ephemeral_cache` says it exists, `cache_breakpoint_models` says how
— the `ephemeral_cache` quirk injects `cache_control` breakpoints only for
`anthropic/claude` and `google/gemini` prefixes, and a type whose caching is a
request-body flag leaves the messages alone (`FIXED_CACHE_TTL_MODELS` drops `ttl` for
Gemini, which honours only the last breakpoint and has a fixed 5-minute TTL). Native
Google providers get Gemini's implicit caching and take no breakpoints.

Schema — `providers/schema.py::provider_schema()` (lru-cached, so a per-process
snapshot) is embedded in `base.html` as `window.PROVIDER_SCHEMA` for
`core/provider-schema.js`: defaults, effort options, forward/visible fields,
capabilities, form config, labels. The ordered type list is `provider_type_options()`.
The sampler getters, `sampler-defaults.js`, form visibility, continue-button
visibility and the prompt-cache predicate all read from it — add per-type UI facts
there, not as new JS conditionals. `capability_filtered_keys()` filters sampler keys.

Client records — `core/provider-store.js` (`ProviderStore`) is the client SSOT for
provider data, seeded in the page and refreshed after every provider CRUD. Selection
ids stay in `StateManager`; the store owns only records. Never reintroduce a
page-load snapshot.

Keys — the `secrets` table is a reusable library (`GET/POST /api/providers/secrets`,
`DELETE /api/providers/secrets/{name}`). A provider stores an ordered list of refs
(`SECRET:<name>`) or raw values in `config.api_keys`, with `config.active_key` naming
the one in use (`provider_key_refs`/`active_key_ref`, switched by
`POST /api/providers/{id}/active-key`); the legacy `api_key` column is a one-element
fallback. Values never leave the server — the list carries a masked preview only. The
picker is `partials/modals/secrets.html` served by `GET /partials/secrets?pick=1`, and
a new key is its own stacked form.

Shared payloads live in a shared module delivered through the adapter (`google_safety.py`
is used by both the Google adapters and the OpenRouter quirk) rather than importing
another SDK.

## Themes and assets

Themes are rows in `themes` (built-ins as `is_system` with fixed `builtin-*` ids,
editable in place; custom CRUD at `/api/themes`; only custom ones delete;
`POST /api/themes/{id}/reset` restores a built-in's seed). `migrate_builtin_themes`
repaints a built-in only while it still matches the old seed. Two global slots,
`dark_theme_id` and `light_theme_id`, written via `PUT /api/settings/theme {slot,
theme_id}`; the app always follows `prefers-color-scheme` and the effective theme is
`characters.theme_id ?? (dark ? dark slot : light slot)`. `window.THEMES` +
`window.THEME_STATE` are embedded server-side and `ui/theme-manager.js` caches both
slot palettes for the flash-free pre-paint in `base.html`. The picker preview is never
saved — dirty state enables Save and prompts before switching themes. `--text-on-accent`
is derived from accent luminance in both places; `--text-faint` is seeded in the
built-ins but not offered by the customizer.

Assets — `core/media.py::asset_url` and its client twin `ui/media-utils.js::assetUrl`
are the only URL builders. Rows store filesystem paths (`assets/…` or wherever
`FOCUS_ASSETS_DIR` points); the tree is served at `/assets`. Templates use the
`asset_url` global, API payloads carry a `url` beside the path, `data-*` attributes
that become images (`data-char-image`, `data-persona-avatar`, `data-persona-image`)
carry the URL. Avatars go through the `avatar()` macro — never `src="/{{ path }}"`.
Filesystem access (`Path(row["image_path"])`) uses the stored value unchanged.

## UI conventions

The full story is `UI.md`; the three rules that decide most arguments:

- Primitives are the closed vocabulary in `static/css/primitives.css` and the only
  file that styles a control. Compose primitives plus the macros (`row_label`,
  `toggle_row`, `slider_row`, `reload_key`, `search_toolbar`, `modal_footer`,
  `tab_bar`, `role_select`) instead of hand-authoring a shape;
  `tests/frontend/test_css_ownership.py` enforces the split. Sizes are `.sm`/`.lg`.
- Button colour follows the verb. Green `.create` for "a new entity now exists" (New,
  Add, Create, Duplicate, Start Chat); indigo `.primary` for commit (Save, Apply,
  Done, Rename, Select, Export); plain `.btn`/`.link` to navigate or dismiss; red
  `.danger` to destroy; amber `.favorite-active` to flag. `.warning`/`.success` exist
  on the same control shapes. Litmus test: one more row after the click? green.
  Save is never green, import is neutral, and opening a picker is navigation.
  `.create` is a tinted plate (`--success-tint`, deepening to
  `--success-tint-strong`), never a solid block.
- A list modal is a banded chassis, a form is not. Bands only work with
  `overlay_class='modal-bands-shell'`; rhythm, inset and the trap list are in
  `UI.md`. Counts live in the rail outside the swap target and are updated from
  `htmx:afterSwap`, never from the `hxGet` promise, which resolves before the swap.

## Gotchas

- A `<script>` in a partial runs on every swap; moving it to the host page makes its
  init run once, before the swapped content exists. Do post-swap wiring in an
  `htmx:afterSwap` hook keyed on the target id (`providers.js` →
  `#providers-modal-body-inner`, guarded by `test-providers-modal-init.js`).
- Writes go through `hxFetch`/`hxJson`/`Refresh.mutate` — two raw fetches can commit
  out of order.
- `x-show` needs `x-cloak`; Alpine loads deferred. `:last-of-type` is not "last with
  this class": `#message-list` holds `#message-list-data` and placeholder stubs, so
  use `querySelectorAll('[data-ui="message"]')`.
- `#message-list` is never htmx-swapped. `message-pruner.js` replaces off-screen
  messages with `.message-placeholder` stubs; resolve a pruned id through
  `MessageIdentity.placeholder()` and keep it out of delete mode's `selectedIds`
  handling, which re-applies chrome when a row scrolls back in.
- Duplicated `data-ui` hooks exist (`data-ui="char-block-count"` on both the editor
  door and the blocks modal head) — scope the query to the modal you mean.
- Two `hxGet`s in flight are not ordered; the `hxFetch` queue is the only serializer.
