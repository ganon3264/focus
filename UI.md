# UI layer — reference

Everything here is about how Focus *looks and lays out*. Behaviour (state flow,
streaming, providers, tools, compaction) is documented in `AGENTS.md`; this file
owns the CSS architecture, the geometry numbers and the traps that keep biting.
It is the detailed companion to `AGENTS.md`: the UI paragraphs there are the
short version, and where the two disagree, this file is right.

---

## 1. Run and verify

```bash
fuser -k 8010/tcp; uv run python main.py --host 127.0.0.1 --port 8010

# static/tailwind.css is generated and gitignored — rebuild after ANY css/template change
./bin/tailwindcss-linux-x64 -i static/tailwind-input.css -o static/tailwind.css

node tests/frontend/grid-audit.js http://127.0.0.1:8010   # the ruler (check count scales with the seeded data)
uv run pytest tests/ -q                                    # backend + all frontend
uv run pytest tests/frontend -q --no-cov -p no:cacheprovider   # skip coverage
```

The ruler is the design gate: panes, chat rows, messages, the modal chassis,
band rhythm, foot symmetry, the theme split. Run it after layout work, not after
every colour tweak.

Screenshot both schemes (`colorScheme` in Playwright) and **zoom in** — clip the
panel, never the full page; 1–2px errors are invisible at 1600×1000.

Untracked scratch at repo root (`paste*.png`, `Screenshot_*`, `todo*.txt`,
`workspace/`, `anima.md`) is the user's. Never `git add -A`.

---

## 2. Layer model

```
variables.css   grid + material + ink/tint tokens     (single source)
tokens.css      Tailwind @theme
base.css        reset, scroll rule, media slot, sortable ghost
animations.css  keyframes only
surfaces/*      shell · sidebar · messages · forms · modals
primitives.css  THE vocabulary — the only file that styles a control
```

Import order (`static/tailwind-input.css`) is load-bearing:
`tailwindcss → variables → tokens → base → animations → surfaces/* → primitives`.
Primitives come last so they win every collision. Surfaces may set **layout** on
their own containers; they may not restyle a primitive.

`tests/frontend/test_css_ownership.py` enforces it: no look property
(background/color/box-shadow/border*/font*/text-transform/letter-spacing) on a
primitive's selector outside `primitives.css`, and no `:not(` anywhere. Layout
properties (flex, width, padding, margin, gap, min-height) ARE allowed on
primitives from a surface — that is how a container spaces its children.

Vocabulary (closed set, shapes fixed, modifiers compose):

```
controls   .btn .key .nav .link .chip .tab .pager
inputs     .field .check .switch
structure  .rail .row .well .frame .panel .card .divider .disclosure .grip
feedback   .toast .tooltip .spinner .empty .note .tag .avatar
```

Intents `.primary .create .danger`; sizes `.sm .lg .xl`; plates `.raised`
(a key in a well) and `.scrim` (a key over imagery — a translucent backing, never
opaque); state classes as JS toggles them (`.active .hidden .expanded .drag-over
.favorite-active …`).

**Type discipline:** engraved type (mono, caps, tracked) belongs to section
headers and modal titles only. Buttons, fields and row values are quiet sans;
rows' data readouts are lowercase mono. `.link` is a sans text action that
earns its affordance from ink and cursor — **no underline** (a rule under the
text turned every text action into a link in a document, not a verb). `.link.meta`
borrows a readout line's voice (mono, faint) for actions that live inside one,
like the message rail's reasoning toggle.

---

## 3. Geometry — two numbers

`--modal-pad` **24** — the panel inset. Title bar padding, band horizontal
padding, the modal foot's horizontal padding. Horizontal only.

`--band-pad` **16** (`calc(var(--u) * 4)`, on `.modal-panel`) — the chassis'
one **vertical** number. Every band pads its content 16 above and 16 below, and
there are no gaps between bands. A band's content therefore always has the same
air above it as below it, whatever it is next to.

### Banded chassis (`.modal-bands`)

```
.modal-bands-shell   (modal_shell overlay_class)  tints head + body chrome
  .modal-band-head        rail: the collection's readout and verbs
  .modal-band-toolbar     optional: search / filter / sort  (no vertical padding of its own — the bands around it supply it)
  .modal-band-lane        the one scrolling plane, full-bleed groove, own 16 padding
  .modal-band-foot        optional closing verb plate, right-aligned verbs
```

- Bands pull out to the panel's inner edges (`margin-inline: -24; padding-inline:
  24`) so grooves and plane edges run full width while content keeps the inset.
- The stack has **no gap**; the first and last children carry the panel edge
  (`.modal-bands > :first-child { padding-top: 16 }` etc.).
- **Chrome is one tint.** The shell paints `--ink-1` on the head and the body
  *once*; bands are transparent over it. `--ink-1` is a translucent colour-mix —
  a band that paints it too doubles the layer and steps ~5 RGB lighter exactly
  where it starts (that was a real, long-lived "why is there a seam" bug).
- **Shell selectors must be direct-child** (`> .modal-panel > .modal-head`) —
  nested modals (provider form inside the banded providers modal, retry modal
  inside that) otherwise inherit `padding-block: 0` and a doubled tint.
- `.modal-head` is `padding: 24` (title inset equally above and below).
  `.modal-foot` (a *footed, unbanded* modal) is `padding: 16 24`.
- A tab strip inside the chassis is chrome: `padding-block: 16 0`,
  `margin-bottom: 0`, **no rule of its own** — the first groove is the one that
  opens the lane. Per-tab banded bodies live in `.modal-tabs > .modal-tab >
  .modal-bands`.
- Never put `.rail` on `.modal-head` (its 24px height collapses the head).

### Rows and settings columns

Three row kinds — using the wrong one is the most common way to wreck a layout:

| class | height | what it is |
|---|---|---|
| `.row` | 32 | a clickable list row: hover band, groove, cursor |
| `.row.sm` | 24 | a compact list row |
| `.row.setting` / `.field-row.setting` | 28 | **one line of a settings column**: caption + control, no groove, 8px inline padding so a hover band has margins |

Modifiers that compose with either row kind:

- `.labeled` — caption takes a fixed 176px (`44u`) column, so every control in a
  column starts on the same line (sliders' tracks, provider inputs).
- `.fit` — the `.field` in the row fills the remaining width.
- `.row-cell` — a composite control (the shared `custom_select`) fills the row.
- `.labeled.tight` — a caption column sized for a side pane (88px, the entity
  editor's identity rows), where the full 176px would leave the control unreadable.
- `.grooved` — a lone row that is a *control*, not the tail of a list: keeps the
  groove's dark bottom line instead of closing on the lit edge (the sidebar's
  preset readout).

Settings columns (`sampler-group`, `tool-settings`, `provider-section`,
`retry-rows`, `theme-colors`) stack their lines with **one gap: 12**. Sliders are
lines too: `slider_row` emits `.field-row.setting.labeled` + range + value, not a
two-line block.

**A caption has one voice.** `.setting > .row-title` owns the caption type
(13px/500/82%) for both row kinds; a `.field-row` has no type of its own, so a
slider caption and a toggle caption drift apart the moment that rule is missing.
Use the macros (`row_label`, `toggle_row`, `slider_row`) instead of authoring the
caption's inline flex by hand. A caption that is prose (an extension parameter's
description) carries `.row-title.wrap` and the row top-aligns its control.

**Dependent settings live in a plate** — `.well` + `gap: 12` + `padding: 4px 8px`
(`.sampler-children`, `.provider-plate`), directly under the row that enables
them. The plate is the nesting cue; nothing is indented into no-man's land, and
the children stay on the row grid. (The old `.branch` indent idiom is gone.)

**Prose fields stay stacked** (`.form-group`: label above control, 4px between).
Textareas and long text are not rows; that split is deliberate. A textarea whose
height is decided for it (a pane filler, or one sized by its own `rows`) carries
`textarea.field.sized`, which turns the native resize grip off — never `.fixed`,
that is a Tailwind utility and utilities beat this file.

**The text modals are block-per-segment.** The message editor renders one
`.msg-block` per segment, each named by a `.rail` that also carries its readout
(length) and its verb (expand) — nothing floats over the text, and the textarea
is auto-sized (`rows`), so it needs no grip. A collapsed block (reasoning) keeps
its rail and hides only its textarea (`.msg-block.collapsed`), so the name and
length stay readable. Attachments are a rail + a `.well` tray: the well **is**
the media gallery (`.well.media-row.msg-attachments-tray`), the thumb layer
dissolves into it (`display: contents`) so the thumbs are the tray's own grid
items, and the tray hugs its rows — one row minimum, 176 cap, scrolls past that.
The entity editor keeps the shared gallery's fixed three-row height because
there the tray sits beside a column whose height it must not decide. The well is
the drop target, so `.well.drag-over` gives the edge for free. The text expander is
the same shape reduced to one field and one foot — the note is the footer's
`hint='note'` variant, the length is a `.row-value` readout, and `Done` (indigo)
is the closing verb.

**The entity editor is two panes.** Identity (Portrait, Name / Group / Theme and
Media as `row.setting.labeled.tight` rows on one caption/control column) beside the
content (Description, Greeting), each pane naming its groups with a `.rail` that also
carries the readouts and verbs (char count + expand, greeting pager). **No
vertical divider**: a short identity column would leave a cut line hanging next
to a tall description. The identity pane ends where its content ends
(`align-self: start`) and scrolls only when the legacy card fields open; the
extras (Custom blocks door, legacy card fields as a `.disclosure.rowlike`) follow
the fields instead of being pinned to the floor, which is what used to leave a
void in the middle of the column. The media gallery is the control of its own
row: a `.well` grid of 48px cells at a fixed 176px height (`overflow-y: auto`)
whose left and right edges connect with the text inputs above, so six references
no longer stretch the identity area; the add tile is its last cell and the
empty-state note spans the tray.

**The provider form is three named groups**, and it is the reference for a
settings column with more than one subject: a `.rail` header ("Connection",
"Credentials", "Advanced") at `gap: 16` between groups, `gap: 12` within one,
one caption column across all of them. Only a group the *type* brings (OpenRouter
routing, Vertex project/region) is a plate, and it sits under the Model row that
makes it appear — not at the bottom of the form, which is what made it look
unrelated. The key list is flat grooved rows (drag handle, label, delete) with
the count in the rail and the create verb in the rail too; an empty list is a
`.provider-keys-empty` note, not a `.row` under the rail's hairline (two
parallel rules 20px apart read as a bug). The retry row carries a readout
(`5× · 2s → 20s`) so the toggle is not opaque. `grid-audit.js` measures it:
rails on the modal inset, one caption column, one control line, one pitch per
group.

---

## 4. Which modal is which shape

| shape | modals |
|---|---|
| banded list | characters, personas, providers, presets, trash, char-blocks, itemizer, prompt arranger |
| tab container, one banded chassis per tab | Advanced (Tools · Extensions · Regex · Structured · Backups) |
| tab container, shared bands + strip inside | Samplers |
| master-detail inside one lane (two independently scrolling columns) | Theme customizer |
| stacked form + foot | provider create/edit, auto-retry, edit entity, edit message, summary, export, regex/structured items, the preset naming dialog, the text expander |

Deliberately not banded: the stacked forms above (a form is not a collection).

---

## 5. Live behaviour you must not break from the UI side

`AGENTS.md` has the detail; these are the UI-adjacent invariants.

- **Refresh registry** (`core/refresh.js`) — one place maps resources to
  surfaces. Mutation sites declare what they wrote; never hand-wire reloads from
  a loader. Entity grids (`characterCards`, `personaCards`) re-fetch through
  `window.reloadCharacterCards` / `reloadPersonaCards`, gated on the modal being
  open.
- **Presets are a collection modal.** The left section's preset control is a
  readout row (`#preset-selector .preset-trigger`) that opens `modal-presets`;
  choosing, creating, renaming, duplicating, deleting and importing all happen
  in that one banded list (`features/presets.js`). The old dropdown-hanging-off-a-
  field and its two separate rename/duplicate dialogs are gone — do not
  reintroduce a second place where presets are managed. The naming dialog
  (`modal-preset-name`) is one form with a `data-mode` of `new | rename |
  duplicate`; its title and verb follow the mode.
- **hxQueue** (`core/hx-queue.js`) — `hxGet`/`hxPost`/`hxFetch` share one
  serializer AND issue from a dedicated `#hx-source` element carrying
  `hx-sync="this:queue all"`. htmx queues per source element with a "last wins"
  policy, so concurrent programmatic requests used to be *silently dropped*; the
  dedicated source turns a drop into a queue. `hxJson(url, method, body)` is the
  JSON write shape (`jsonOpts` when the options are composed with
  `Refresh.mutate`), so no call site re-authors the header + stringify. Raw
  `fetch` is reserved for transports the queue cannot carry (SSE readers, stop
  requests with their own timeout, binary downloads, one slow external command)
  and each carries a `// raw: <reason>` marker that
  `tests/frontend/test_fetch_guard.py` enforces.
- **Never short-circuit an htmx request you do not have to.** `ui/confirm.js`
  only intercepts `htmx:confirm` when there is a question. Intercepting
  unconditionally resolves `htmx.ajax`'s promise without sending anything, which
  both lies to hxQueue and races htmx's queue.
- **Streaming DOM** — message markup has one source (macros →
  `partials/chat/message-templates.html` → `message-builder.js` clones; fixture
  `tests/frontend/fixtures/message-templates.html` is guarded). Never
  htmx-swap `#message-list`; `refreshMessageList` reconciles in place.
- **Modal lifecycle** — everything opens/closes through `ModalController`.
  Dirty tracking is opt-in via `modal_shell` params; save handlers close with
  `{ discard: true }`.

---

## 6. Traps that have actually bitten

- **A translucent token painted twice is a seam.** See §3. Applies to any
  `color-mix(… transparent)` token, not just `--ink-1`.
- **Descendant selectors on a shell class leak into nested modals.** Always
  scope through `> .modal-panel >`.
- **`.hxGet`'s promise can resolve before the swap.** Wire post-swap work
  (Sortable, counts) on `htmx:afterSwap` keyed on the target id.
- **A partial gets exactly one `<script>`.** A duplicated block is valid HTML;
  the browser parses half and the page loses its wiring.
  `test_partial_has_one_inline_script` guards it.
- **Writes must be serialised** — two `PATCH`es fired back to back can commit out
  of order. Route them through `hxFetch` / `Refresh.mutate`.
- **`custom_select`'s `extra_classes` land on the trigger button**, not its
  `w-full` wrapper. Wrap it in `.row-cell` to size it inside a row.
- **`x-show` needs `x-cloak`** (Alpine is deferred); `[x-cloak]` is defined in
  `tailwind-input.css`. Prefer it over `style="display:none"`.
- **`:has()` is not a substitute for an explicit flag** in a swapped body —
  nested modals make `:has(.modal-foot)` match.
- **Tailwind utilities lose** to unlayered surface/primitives rules. If a utility
  "does nothing", a primitive already decided it.
- **No `:not(`** anywhere (`test_css_ownership.py`).
- **A row missing its last verb reserves the slot** (`verb_slot()`).
- **Rows inside a `.well` or `.card` paint no groove** (primitive rule).
- **Don't rename** `id`, `data-ui`, `data-action`, `hx-*`, or the state classes
  JS toggles (`hidden active disabled expanded details drag-over processed ready
  copied favorite-active reasoning-open message-placeholder toast*`).
- **Screenshot with a hover applied** when touching rows — the hover band is
  where the "no padding / 1px peek" class of bug shows up.

---

## 7. User's standing preferences

- **Symmetry over cleverness.** A band, a row, a caption gets the same air above
  as below, or it reads as a bug. Mixed 24/12 rhythms were rejected outright.
- **One inset, one rhythm.** The modal inset is 24 horizontally; the chassis'
  vertical rhythm is one number. Do not introduce a third.
- **Hover and focus targets need margins around their text.** A highlight flush
  with the caption looks cheap.
- **A caption is a caption.** Same size, weight and colour on every line of a
  column, whatever control sits beside it.
- **Do not preserve a bad base.** Rebuild the structure when the structure is
  the problem — polishing an invalid shape produces polish that still reads
  wrong. (The provider form and the sampler were both rewritten, not nudged.)
- **Two lines beat four things on one baseline.** Entity rows carry title over
  meta; a row that needs a readout and verbs gets the height for it.
- **The grip carries the role** in block lists, not the row's left edge.
- Destructive verbs are ink + edge, not red washes; create is a tinted plate,
  never solid. One create per surface where possible.
- Separators are grooves (dark + lit line), never a lone dark line. Carets and
  separator dots are drawn (`.caret-mark`), never glyphs.
- Hairlines are `inset box-shadow`, never `border`. Geometry on the 4px grid.

---

## 8. Known debt

1. **Overlay ruler gap** — `grid-audit.js` measures panes, chat rows, messages,
   the modal chassis, band rhythm, foot symmetry and the theme split; toasts,
   the hint tooltip and the lightbox are still eyeballed.
2. **Form read/write** — ~15 implementations, ~100 hardcoded ids. Biggest churn,
   no visible payoff; leave it unless a feature needs it.
3. **The retry modal's booleans are `.check`, every other setting is a
   `.switch`** — they are `<input type=checkbox>` read by id from
   `providers.js`, so switching them means teaching `refreshRetryHint` /
   `populateRetryForm` the `.switch` shape.
4. **`.link` users still to eyeball after the underline removal** — summary
   boundary button, itemizer reasoning toggle, extensions "Configure", the
   arranger's "Restore default". The message rail's reasoning toggle is settled
   (`.link.meta`).
