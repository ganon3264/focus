# Handoff — UI overhaul

Branch `refactor/consolidate-ui`, off `master` (d7b89ad). The skin pass is
closed (steps 0–5), the character editor has its card blocks and card fields
back (step 6), every list modal runs on the banded chassis (steps 7–9), and the
arranger/provider polish is in (`17230c8`…`ffa00bc`). 1449 backend +
292 frontend tests green; grid audit **186/186** (panes, messages, the modal
chassis, field/control centre lines, and the band rhythm of every list modal).

Read this, then `static/css/primitives.css` (the closed vocabulary), then
`PRIMITIVE-MAP.md` (the class audit that produced it). The CSS import order in
`static/tailwind-input.css` is the load-bearing part of the architecture:
base → surfaces → primitives, so primitives win every collision.

---

## 1. What this branch is

**A. Fragmentation cleanup — done.** Same component authored in two or three
files, markup duplicated between Jinja and JS, JS using class names as its DOM
API. Resolved in:

| commit | what |
|---|---|
| `86a141e` | 201 dead cross-file CSS declarations, `.card` family, 8 macros, deleted `/characters` `/personas` `/providers` pages |
| `aab1fd3` | every JS DOM lookup is a `data-ui="<name>"` hook (142 converted), guard test in `test_frontend.py` |
| `3e44407` | message markup has one source: macros → `partials/chat/message-templates.html` → `message-builder.js` clones. Fixture kept in sync by `test_message_template.py` |
| `76c5d3f`, `e2c0502` | every overlay opens/closes through `ModalController` |

**B. New skin — rebuilt primitive-first.** The first skin pass was abandoned
because it produced *overrides* instead of replacements. `PRIMITIVE-MAP.md` maps
all 243 legacy classes onto one closed vocabulary.

| step | state | what |
|---|---|---|
| 0 | done | `PRIMITIVE-MAP.md` audit |
| — | done | `primitives.css`, tokens repaired, `:not()` ladders + `.btn*` legacy family deleted (`2796b9d`) |
| 1 | done | shell + both sidebars (`70221c5`), `surfaces/shell.css` |
| 2 | done | messages + composer (`2b1feb5`), `chat.css` `input.css` `design.css` deleted |
| — | done | polish rounds: grip LED, well rows, disclosure plates, reasoning, prose metrics, composer |
| 3 | done | modals + forms (`70263f1`, `275750f`, `b4d74a7`, `72bb243`), `surfaces/modals.css` `surfaces/forms.css`, `instrument.css` `components.css` `layout.css` deleted |
| 4 | done | overlays (`fe30ea1`): toast stack is the `.toast` primitive (`.key.sm` verbs), `#hint-tooltip` is a `.tooltip` toggled by `.hidden`, lightbox is `modal-overlay` + `panel` + `modal-head`; `animations.css` keeps only keyframes |
| 5 | done | `tests/frontend/test_css_ownership.py` — no surface authors a primitive's look, no `:not()` in any stylesheet. Two real violations it flushed out: `.preset-menu .row { font-size }` (now `.row.sm`) and the reasoning block's `:not(:has(summary))` (now `.reasoning-block.headless`) |
| 6 | done | character editor rebuilt + card blocks ported back (`1bbfe59`, see §6) |
| 7 | done | entity list modals (characters / personas) rebuilt as a banded chassis: rail + toolbar + list plane + foot, hover-revealed verbs, group tags (`9165f8d`, `9b92cf3`) |
| 8 | done | the banded chassis is a vocabulary (`modal-bands*`) and the rest of the list modals adopted it: providers, trash bin, custom blocks, prompt arranger (`6e74a8e`) |
| 9 | done | band rhythm is a rule the ruler enforces (rail → next band = 12), the itemizer joins the vocabulary, and `grid-audit.js` measures every banded modal (`96a212a`) |
| 10 | done | arranger + provider polish: role on the grip, two-line provider rows, one-column expanded block body, previews as control-height readouts, verb slots (`17230c8`, `ad4a4bf`, `bcd3ce7`, `ffa00bc`) |

---

## 2. The primitive contract

Closed set — shapes are fixed, modifiers compose:

```
controls   .btn .key .nav .link .chip .tab .pager
inputs     .field .check .switch
structure  .rail .row .well .frame .panel .card .divider .disclosure .grip
feedback   .toast .tooltip .spinner .empty .note .tag .avatar
```

- Intents: `.primary .create .danger .warning .success`. Sizes: `.sm .lg .xl`
  (`.key.xl` = 48 — the character editor's reference-media tile and message
  media; a block body's media tray is `.key.lg` = 32), plus `.raised` on `.key`
  (a key that needs a plate of its own inside a well).
- State is class-driven exactly as JS toggles it: `.active .disabled .expanded
  .hidden .drag-over .copied .favorite-active .on .caret-open`.
- `.row` slots: `.row-title .row-meta .row-value .row-label .row-actions`;
  modifiers `.sm .inset .flat` (no horizontal padding, for settings rows inside a
  form column) and role edges `.role-user .role-assistant .role-system`.
- `.field` modifiers: `.sm .num` (intrinsic numeric readout) `.ghost` (in-place
  edit, underline only) `.select` (picker-shaped button, with a caret) `.swatch`
  (chip) `.color` (palette well) `.danger` (failed parse).
- `.panel` is the floating layer: flat `--surface-2` fill, hairline ring, deep
  shadow. No gradient — a floating plate reads by its edge and its shadow.
- **Intent is ink + edge, or a tinted plate** (`.create`/`.toast-success`), never
  a wash over a raised control.
- **Fill is a signal in exactly one place**: `.grip` — the drag state (`.on`,
  accent) or the role of the block it holds (`.role-*`, matching the role
  colours; system takes the solid accent because `--edge` is a hairline tone).
- **A surface may set layout on its own container; it may not restyle a
  primitive.** Named slots exist for this: `.disclosure-title`/`-meta`,
  `.row-*`, `.rail-actions`. Never select on child position inside a primitive.
- Hairlines are `inset box-shadow`, never `border`. Geometry is multiples of
  `--u` (4px).

### Tokens (`variables.css`)

Grid: `--u` 4, `--inset` 12, `--gutter` 8, `--rail-h` 24, `--row-h` 28,
`--control-h{,-sm,-lg}` 28/24/32, `--hair-w` 1, `--radius-panel` 0,
`--radius-control` 2.

Material: `--mat-raise` (a plate's own lit/shaded edges), `--mat-lift` (`--mat-raise` + the 1px cast shadow, **floating layers only**), `--mat-raise-fill`, `--mat-inset`, `--mat-well`,
`--mat-brush`, `--mat-hi/shade/lo/edge/glow`, `--hair-dark`/`--hair-lit`,
`--hair-groove`.

Ink/tint: `--ink-1/2`, `--hair`, `--hair-strong`, `--engrave`, `--tint-1/2/3`,
`--edge`, `--danger-*`, `--success-*`.

Font metrics: `--prose-ink-lead: 7px`, `--prose-ink-trail: 4px`. Re-measure if the
body face or rhythm changes.

---

## 3. CSS architecture

```
variables.css   grid + material + ink/tint + font metrics   (single source)
tokens.css      Tailwind @theme (fonts/radius/shadows)
base.css        reset, scroll rule, media slot, machine type, sortable ghost
animations.css  keyframes only (overlays are primitives now)
surfaces/shell.css      chassis, pane widths, collapsed grips
surfaces/sidebar.css    sections, preset selector/menu, variables, tools, status, chat rows, footer
surfaces/messages.css   chat column, message frame/rail/screen, prose scope, composer
surfaces/forms.css      .form-group, field rows, textarea host, branches, help mark
surfaces/modals.css     modal chassis, the banded-list vocabulary + rhythm, every modal's geometry
primitives.css  THE vocabulary — the only file that styles a control
```

Import order: `tailwindcss → variables → tokens → base → animations →
surfaces/* → primitives`. Surfaces are unlayered and come after the keyframes;
primitives come last.

**Step 3 deleted the last legacy files.** `instrument.css`, `components.css` and
`layout.css` are gone; the tokens they still owned live in `variables.css` /
`base.css`, and the form defaults they carried are `.field` and `.base`.

### Modal chassis (`surfaces/modals.css`)

- `.modal-overlay` = scrim + centring grid, 24px padding.
- `.modal-panel` = `.panel` + a `--modal-pad: 24px` local token + column layout.
- `.modal-head` = engraved title (11px mono, 12em tracking) + `.key.sm` close,
  `padding: 24 24 16`, closed by a full-bleed groove. **It is its own element;
  never put `.rail` on it** (`.rail`'s 24px height beats any head height and the
  title ends up jammed against the top edge — that was a real bug).
- `.modal-body` = the single scroll lane, `padding: 24`, no scrollbar gutter (a
  reserved lane on one side is what makes the right margin stop matching the
  left). Inner scroll lanes get `padding-right: 0` + `scrollbar-gutter: auto`.
- `.modal-foot` (the `modal_footer` macro) = full-bleed plate, `padding: 16 24
  24`, `margin: auto -24 0`, `position: sticky; bottom: 0`. It owns the bottom
  inset — which is why a modal that has a foot passes **`foot=true`** to
  `modal_shell` (the body then drops its `padding-bottom`). The flag is explicit
  on purpose: `:has(.modal-foot)` is wrong because the swapped modal bodies
  (providers, arranger) contain their own nested modals with feet.
- `grid-audit.js` now measures it: title on 24/24, body pad 24, content clears
  the floor by 24, foot buttons 24/24, entity rows 32 with a 24 avatar, tab
  strip full-bleed, and every field/control pair sharing one centre line.

### Banded list modals (`modal-bands*`)

A modal whose body is a list is a chassis of bands, not one scroll island:

```
.modal-bands-shell  (modal_shell overlay_class) → tints .modal-head into the chrome
.modal-bands        the flex column inside .modal-body
  .modal-band-head      readout rail: count + the collection's verbs
  .modal-band-toolbar   optional search / filter / sort row
  .modal-band-lane      the one scrolling plane (--surface), opens with a groove
  .modal-band-foot      optional closing verb row (Trash Bin, Add Block)
```

- Bands pull out to the panel's inner edges (`margin-inline: -var(--band-pad)`)
  and pad back in, so grooves and plane edges run full width while the content
  keeps the modal's one inset. **The first and last bands absorb the body's own
  padding** — a tinted strip that is not a band is discoloration.
- Chrome is one tint (`.modal-head` + head/toolbar/foot bands); the lane is the
  only other value. A lane that is the last child closes on the panel floor.
- **Vertical rhythm:** head band `24` above its rail and **`12` below it** (the
  air every following band inherits); toolbar `0` top / `12` bottom; lane `8`
  above its first row; foot `12` above its verbs and `24` to the floor. The
  ruler asserts `rail → next band = 12` on characters, providers, itemizer and
  arranger — that check catches the "no margin at the top" regression.
- Users: characters, personas, providers, trash bin, custom blocks, prompt
  itemizer, prompt arranger. Deliberately *not* banded: the Advanced modal (tab
  container), the theme customizer (master-detail), the export form.

### Entity rows

Characters and personas share `.row.entity-row` in two column-major lanes
(`.entity-list` + `column-rule`). Anatomy follows the right-pane chat row:
avatar (24) → `.row-title` → `.row-meta` (the group as a `.tag`) → verbs in
flow. Verbs are hover-revealed (`reveal-verbs`); a favourite's star stays lit
because it is state. Providers are **one column, two lines**: name over
`type · model`, then the balance readout and the verbs, at 48px
(`.entity-row.provider-row` — a lone `.provider-row` loses the cascade).

---

## 4. Verification

```bash
fuser -k 8010/tcp; uv run python main.py --host 127.0.0.1 --port 8010

# after any CSS change — tailwind.css is a generated, gitignored artifact
./bin/tailwindcss-linux-x64 -i static/tailwind-input.css -o static/tailwind.css

node tests/frontend/grid-audit.js http://127.0.0.1:8010   # the ruler (186 checks)
uv run pytest tests/ -q
uv run pytest tests/frontend -q --no-cov -p no:cacheprovider
```

Screenshot both schemes after any visual change (`colorScheme` in Playwright).
**Zoom in** — `locator.screenshot()` / a clip on the panel, not full-page shots;
the 1–2px errors are invisible at 1600×1000.

---

## 5. Environment / state

- Dark theme slot in the local DB is `builtin-instrument` (lifted mid-grey
  chassis, amber accent). Near-black themes cannot show bevels.
- `Slate` and `Instrument` seeds are lifted mid-greys in `focus/db/themes.py`;
  `tests/api/test_themes.py` asserts those values.
- Untracked scratch at repo root (`paste*.jpg`, `Screenshot_*.png`, `anima.md`,
  `todo*.txt`, `workspace/`) belongs to the user. **Never `git add -A`.**
- Browser caches the resolved theme in `localStorage['focus-theme-state']`.
  "It didn't change" is usually a stale reload.

---

## 6. Character editor + card blocks (step 6)

Dropping the `/characters` page left two holes in the modal: the custom block
editor and `personality`/`scenario`/`mes_example` (the API always accepted them;
the prompt's `char_personality` sentinel had no way to be filled). Both are back,
rebuilt on the primitives:

- **One field column.** Identity plate (avatar + reference-media strip beside it)
  → Name → Group → Theme → `Card fields` disclosure → `Custom blocks` door on the
  floor of the column. The old layout put Theme at the column edge while Name and
  Group were indented by the avatar; now every control is on one left edge and
  the media strip uses the space next to the avatar instead of the column's
  bottom third. `padding-bottom: var(--inset)` on `.edit-entity-body` restores the
  gap above the foot plate (the body drops its own padding when `foot=true`).
- **Card fields** are a `<details class="disclosure">` inside the form, so they
  submit and dirty-track with everything else.
- **Custom blocks** are a separate 720px modal on `z_index: 200`, opened from the
  door (which shows the count from `data-char-blocks` on the card's edit button).
  The list reuses the arranger anatomy and the arranger's row CSS; the body is a
  role select + a content textarea with an expand key, plus the block's own media
  row. Everything PATCHes on change — no Save verb, matching the arranger.
- Backend additions: `POST /api/characters/{id}/blocks/reorder` (`{ids}`),
  `GET /partials/char-blocks/{id}`, `GET /partials/char-block/{id}/{block}`.
  Tests: `TestCharacterBlocks` (api), `test-char-blocks.js` (29), plus
  `test-edit-entity.js` coverage for the card fields + count.

The traps this step produced are in §8 (swap timing, write ordering, band
geometry, `custom_select`'s wrapper).

---

## 7. Remaining work

What is left is the debt the pass deliberately did not take on:

- **Form read/write** has ~15 implementations and 102 hardcoded IDs.
- **Registry bypasses**: ~75 raw `fetch` vs 31 `hx*` calls.
- `grid-audit.js` measures panes, messages, the modal chassis, field/control
  centre lines and the band rhythm of every list modal — toasts, the hint
  tooltip and the lightbox are still eyeballed only.
- `CharacterStore` still has no callers (the card-block editor did not need it;
  it is a server-rendered list like the arranger).

---

## 8. Traps learned the hard way

- **`.message` must carry `.frame`.** The look comes from the primitive.
- **A banded modal's chrome is one field.** Tinting the head/toolbar/foot bands
  but not the body leaves a 24px strip of panel fill above the rail and below
  the foot — the discoloration the user marked. Tint `.modal-head` **and**
  `.modal-body`; the lane paints its own plane on top.
- **The `hxGet` promise resolves before htmx swaps.** Wiring a Sortable, or
  reading a fresh count, inside `.then` acts on the node that is about to be
  replaced. Use `htmx:afterSwap` keyed on the target id (char blocks, arranger
  rail).
- **Writes must be serialised.** Two `PATCH`es fired back to back (role then
  enable) can commit out of order on the server. `hxFetch` puts block writes on
  the same queue as the reloads.
- **A partial gets exactly one `<script>`.** A duplicated block is valid HTML,
  so nothing complains — the browser parses half of it and the page renders with
  its wiring gone. `test_partial_has_one_inline_script` guards it (that bug
  shipped once and the list silently lost sorting/filtering).
- **`custom_select`'s `extra_classes` land on the trigger button**, not its
  `w-full` wrapper — a `flex` basis passed there never sizes the wrapper. Wrap the
  macro in a `<div class="arranger-select">`.
- **A readout that sits beside a control takes the control's height.** The
  preview wells were 32 (line + padding) next to a 28 picker; and a `pre-wrap`
  preview turned the template's own newlines into blank lines. One line, `nowrap`,
  explicit `--control-h`.
- **An expanded block body is one column, not four stacked blocks with their own
  margins.** It used to be `.arranger-body` (padding 8 0 0 20) → a `.row` with
  `margin-top: 4` → a `.field-row` with none → `.arranger-media` with
  `padding: 8 0 0 20`: four different indents and three different gaps. Now one
  `.arranger-expand` wrapper owns the inset and the gap; children carry none.
- **A preview is not a field.** `.preview-out` used `white-space: pre-wrap`, so
  the template's own newlines and indentation around the block content became
  visible blank lines and a one-line block previewed 80px tall. It is `nowrap`
  with an ellipsis now; the template whitespace inside the div is trimmed too.
- **A row missing a verb shifts the rest.** The arranger's switch sat 28px
  right on rows with no delete key. `verb_slot()` renders an invisible `.key.sm`
  so the cluster keeps its column (same reason the provider rail is `flush`).
- **A surface override of a primitive's geometry loses silently.** `.row.sm`
  (primitives, imported last) beats `.preset-menu .row { min-height }` at equal
  specificity — so restyle by picking the right modifier, not by re-declaring.
  The provider row's 48px height needs `.entity-row.provider-row` for the same
  reason: a lone `.provider-row` loses to `.row`'s 32px.
- **`scrollbar-gutter: stable` moves the right edge in.** A scrolled list and a
  scrolled-out header beside it need the same reserved lane, or their trailing
  keys sit 10px apart. The preset menu reserves it on the rail too.
- **`test_css_ownership.py` is the gate, not a linter.** It proves itself on a
  synthetic violation; if it goes green on a `static/css` tree it cannot parse,
  `test_guard_scans_the_real_surfaces` fails first.
- **`.rail` on `.modal-head` is a bug**: `.rail`'s 24px height wins, the head
  collapses, the title touches the panel top while the sides keep their padding.
  Same class of bug as `.divider` on a header (it sets `height: 1px`).
- **`.field` sets `display: block; width: 100%`**: a Tailwind `flex`/`w-auto` on
  it loses (utilities are layered). Use `.field.select` for a picker-shaped
  button and `.field.num` for an intrinsic-width readout; give it a `flex` basis
  if it must share a row (`.arranger-select`).
- **A modal's inner scroll lane must not keep the app's `padding-right` gap** or
  the right margin stops matching the left. `surfaces/modals.css` resets both the
  padding and the gutter inside `.modal-body`.
- **`:has()` is not a substitute for an explicit flag** in a swapped body: the
  providers/arranger bodies contain nested modals, so `:has(.modal-foot)`
  matches. `modal_shell(..., foot=true)` is explicit.
- **A control must not paint outside its box.** `--mat-raise` used to end with
  `0 1px 0 var(--mat-edge)`, so every button sitting beside a field was 1px
  lower than it (its cast shadow). The drop is now `--mat-lift`, used only by
  `.frame` — things that float on the page, never a control on a baseline. The
  ruler asserts field/control centres.
- **An inline-flex control in a plain block wrapper sits on a line box**: a
  `.btn`/`.key` inside `<div class="relative">` is baseline-aligned, so it lands
  2px lower than its neighbours and adds a descender. The wrapper must be `flex`
  (that was the "sort button is out of alignment" bug).
- **The help mark is one shape.** A question mark on a square plate; never a
  circle glyph inside a square, and never a plate inside a key (use
  `.hint-glyph` there — the key is already the plate).
- **The pre-answer reasoning block has no head.** Its toggle lives on the rail
  (`message_meta(..., show_reasoning)`); the index-0 block is a headless
  `.disclosure` hidden with `display: none` while its content is `.hidden`.
  Its "follow" is `#reasoning-sticky-host`, not `position: sticky`.
- **Disclosures need a ring.** A fill alone disappears on themes where
  `--surface` and `--mat-well` are the same value.
- **Only the rail's own caret turns.** `.message.reasoning-open .message-meta
  .reasoning-chevron` — an unscoped rule flipped every disclosure in the message.
- **`textarea` needs `rows="1"`.** Height is driven by `scrollHeight` vs the CSS
  `max-height`.
- **Chat rows are measured against their scroll lane**, not the pane.
- **The composer floats**: 10u bottom padding; the status panel grows by 12px per
  extra row.
- **Tailwind utilities lose** to unlayered surface/primitives rules.
- **Message markup is single-sourced**; regenerate
  `tests/frontend/fixtures/message-templates.html` when the macros change.
- **The pruner stores `offsetHeight`**; the DOM shape JS queries may not change.
- Don't rename `id`, `data-ui`, `data-action`, `hx-*`, or the state classes JS
  toggles (`hidden active disabled expanded details drag-over processed ready
  copied favorite-active reasoning-open message-placeholder toast*`).

---

## 9. User's explicit preferences (learned the hard way)

- **One inset, everywhere.** A modal title that has 24px at the sides and 4px on
  top is the kind of thing that gets the whole pass rejected. Head, body and foot
  share `--modal-pad`; the ruler checks it. The same applies inside a body: one
  wrapper owns the inset and the gap (`.arranger-expand`, the band rhythm), never
  four children with their own margins.
- **A list modal must feel composed, not like a wall of rows**: distinct bands,
  a lane on its own plane, no scroll fade over it, verbs that keep one column.
- **Two lines beat four things on one baseline.** Providers carry name over
  type · model; a row that needs a readout *and* verbs gets the height for it.
- **The grip carries the role** in block lists; the row's left edge does not.
- **A preview is a readout**: one line, control height, opens the editor. It is
  never a small input that grows with its content.
- Entity lists follow the right-pane chat row, not a table: title + readout +
  hover-revealed verbs. No wall of red delete keys.
- Compact chat list: one line per row, fixed 80px readout column (date over
  persona); persona must stay visible.
- No red washes on destructive controls in general — but **intent plates**
  (create, toast success/error, primary key) carry their hue across the whole
  surface.
- No corner/bracket motifs, no rounded cards. Controls get `--radius-control` (2),
  panels stay square.
- Everything aligned; if something is 1–2px off it *will* be noticed. Gaps next to
  prose are compensated by font metrics, not eyeballed.
- Separators are grooves (dark line + lit line under it), never a lone dark line.
- Row content gets interior padding; an indent belongs in `padding`, not in the
  row's box (except `.row.flat`, where aligning with the form column wins).
  Rows inside a `.well` paint no groove.
- Carets and separator dots are drawn (`.caret-mark`), never glyphs.
- Message frames: heavier rather than lighter. Disclosures are plates.
- Composer: 14px body, floating clear of the floor, must not resize on the first
  keystroke.
