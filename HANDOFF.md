# Handoff — UI overhaul

Branch `refactor/consolidate-ui`, off `master` (d7b89ad).
Last commit `7433320`. 1416 tests + 269 frontend tests green, grid audit
140/140.

Read this before touching CSS or templates. Then read `static/css/design.css` —
it is the contract, not a suggestion.

---

## 1. What this branch is

Two tracks, in order:

**A. Fragmentation cleanup — done.** The repo had the same component authored in
two or three files, markup duplicated between Jinja and JS, and JS using CSS
class names as its DOM API. That is all resolved:

| commit | what |
|---|---|
| `86a141e` | 201 dead cross-file CSS declarations, `.card` family, 8 macros (toggle, slider row, avatar, search toolbar, modal footer, tab bar, empty state, in-chat controls), deleted `/characters` `/personas` `/providers` pages |
| `aab1fd3` | every JS DOM lookup is a `data-ui="<name>"` hook instead of a class selector (142 converted); guard test in `test_frontend.py` |
| `3e44407` | message markup has one source: macros in `templates/macros.html` → rendered once into inert `<template>`s by `partials/chat/message-templates.html` → `message-builder.js` clones and fills. Fixture kept in sync by `test_message_template.py::test_message_templates_fixture_is_current` |
| `76c5d3f`, `e2c0502` | every overlay opens/closes through `ModalController`; confirm/lightbox/crop/option-picker/fetch-models/secrets/trash all use `modal_shell`. `ModalController.onClose(id, fn)` exists for teardown |

**B. New skin — reset to primitives (in progress).** The surface-by-surface
pass was abandoned after the shell, both sidebars and messages were done. It
produced *overrides*, not replacements: 1642 new lines against 153 deleted, 37
selectors owned by two files, and `:not()` ladders (`.btn-secondary:not(.tool-tile)`)
that made `.btn-secondary` mean two different things. That is why the left
sidebar's tiles and the right sidebar's Trash Bin looked like different apps.

`PRIMITIVE-MAP.md` is the audit that replaced it: all 243 legacy classes mapped
to one closed vocabulary, 57 flagged layout-only, 12 open decisions, 25
protected JS hooks. Read it before writing CSS.

| commit | what |
|---|---|
| `329409e` … `34d27b3` | first skin pass: shell, messages, composer |
| `58bd82c` … `7433320` | shell + both sidebars (kept as calibration reference) |
| `PRIMITIVE-MAP.md` | class → primitive audit of the whole app |
| `primitives.css` | the closed vocabulary + token repair + ladder deletion |

---

## 2. Design contract

### Grid

One unit, `--u` = 4px. Every size in the app is a multiple of it. Tokens live in
`static/css/variables.css`:

| token | value | use |
|---|---|---|
| `--inset` | 12 | panel padding, pane inset |
| `--gutter` | 8 | gap between controls |
| `--rail-h` | 24 | section rails |
| `--row-h` | 28 | generic rows |
| `--control-h` | 28 | control height |
| `--control-h-sm` | 24 | dense icon keys |
| `--control-h-lg` | 32 | primary controls, message rail, chat rows |
| `--hair-w` | 1 | hairlines |
| `--radius-panel` | 0 | panels/screens |
| `--radius-control` | 2 | controls |

**Hairlines are `inset box-shadow`, never `border`.** A border adds to the box;
1px per row is exactly how a 16-row panel drifts off the ruler (this really
happened). When converting a border to a shadow, also set `border: none` —
leaving the old border in place is the other half of that bug.

Text that must line up across rows uses fixed line boxes whose sum is the row
height, so truncation can't change a row's geometry.

### Material

Four recipes, all theme-derived (`color-mix` against `--surface`/`--bg`) and
declared in `variables.css`:

| token | meaning |
|---|---|
| `--mat-raise` | box-shadow stack: lit top, shaded bottom, outer bottom line |
| `--mat-raise-fill` | `linear-gradient(--mat-glow, --mat-shade)` |
| `--mat-inset` | recessed: inner top shadow + lit bottom lip |
| `--mat-well` | fill for recessed surfaces |
| `--mat-brush` | 1.2% vertical brushing, chassis surfaces only |

Rules:
- **Raised = touchable, flat = readout.** Buttons/keys get the bevel; screens,
  wells, status panels and the chat-list readout column stay flat.
- **Fill is never the state indicator.** State is bevel + ink. Red is ink and
  edge, not a wash (a translucent danger tint over the raise gradient reads as
  "flat web hover" and was explicitly rejected).
- Matte = low amplitude. Do not crank the gradients.
- Messages carry *more* depth than controls: `--mat-glow +9%`, `--mat-shade
  −10%`, `--mat-well` mixes surface→bg then darkens 6% (works on light themes
  without turning into a grey slab). These overrides are scoped to `.message` in
  `surfaces/messages.css` on purpose — do not promote them globally.
- Depth is 1px. No big shadows except the floating modal layer.

### Typography / alignment
- Labels: mono caps, tracked, engraved (`text-shadow: 0 1px 0 --mat-lo`).
- Readouts/values: mono, `font-variant-numeric: tabular-nums`.
- Prose: Ronzino, 24px line rhythm.
- Readouts that sit next to a larger name are **optically centred**, not
  baseline-aligned (baseline makes small type hang low).
- Panes share rail baselines: the left and right section titles start at the same
  y and the same inset.

---

## 3. CSS architecture — target layout

```
variables.css     grid + material + ink/tint scales   (single source)
tokens.css        Tailwind @theme (fonts/radius/shadows)
base.css          reset
primitives.css    ← THE closed vocabulary; the only file that styles a control
surfaces/shell.css
surfaces/sidebar.css
surfaces/messages.css   (incl. the prose scope — `.markdown-content` is a
                         scope, not a primitive)
surfaces/modals.css
surfaces/forms.css
surfaces/overlays.css   (toasts, tooltips, lightbox, option picker)
```

**To be deleted:** `layout.css`, `chat.css`, `input.css`, `components.css`,
`animations.css` (1910 lines, layered), `instrument.css` (legacy skin, still the
owner of modals/forms), and `design.css` (the calibration file, once its left
sidebar rules are re-expressed against primitives).

### Primitive contract

- Shapes are fixed and finite — `.btn .key .nav .link .chip .tab` | `.field
  .check .switch` | `.rail .row .well .frame .panel .card .divider .disclosure
  .grip` | `.toast .tooltip .spinner .empty .note .tag .avatar .pager`.
  Modifiers compose: `.sm .lg`, `.primary .create .danger .warning .success`.
- **A surface may set layout on its own container; it may never restyle a
  primitive.** If a surface needs a different look, the primitive is wrong.
- No `:not()` ladders, no surface-scoped overrides of a primitive, no `border`
  for hairlines. One owner per selector.
- Intents are ink + edge, never a wash over the plate (a translucent fill on the
  raise gradient reads as flat web hover).
- State class names are fixed because JS toggles them: `active`, `disabled`,
  `expanded`, `hidden`, `drag-over`, `copied`, `favorite-active`,
  `message-placeholder`, `reasoning-open`, `processed`, `ready`, `details`,
  `toast`, `toast-text`, `toast-actions`, `toast-leave`, `toast-btn`. They must
  resolve identically in every primitive that carries them.

---

## 4. Verification

```bash
# app (already running on :8010 during development; don't start a second one
# on the same port)
fuser -k 8010/tcp; uv run python main.py --host 127.0.0.1 --port 8010

# after any CSS change (tailwind.css is a generated, gitignored artifact)
./bin/tailwindcss-linux-x64 -i static/tailwind-input.css -o static/tailwind.css

# the ruler — measures the live app in Chrome, fails on off-grid boxes
node tests/frontend/grid-audit.js http://127.0.0.1:8010

# tests
uv run pytest tests/ -q
uv run pytest tests/frontend -q --no-cov -p no:cacheprovider
```

`grid-audit.js` reads `getBoundingClientRect()` for panes, rails, chat rows, tool
tiles, status rows, message frames/screens and the composer, then asserts:
multiples of 4; sibling rows agree on top/height; pane insets; left/right rail
baselines; preset well == New Chat box; message frames on the 800px column and
screens inset exactly 8; composer on the message column. **Add selectors for
every new surface** — a check that is not in the file does not exist.

Playwright is installed (`chromium.launch({ channel: 'chrome' })`); Chrome is at
`/usr/bin/google-chrome`. Screenshot both colour schemes; the theme is user
configurable, material must work on light and dark.

---

## 5. Environment / state

- Dark theme slot in the local DB was switched to `builtin-instrument` (lifted
  mid-grey chassis, amber accent). The user's custom "Midnight purple" theme is
  untouched. Near-black themes cannot show bevels — no luminance headroom.
- `Slate` and `Instrument` seeds were lifted to mid-greys in
  `focus/db/themes.py`; `tests/api/test_themes.py` asserts those values.
- Untracked scratch at repo root (`Screenshot_*.png`, `anima.md`, `todo*.txt`,
  `workspace/`) belongs to the user. **Never `git add -A`.**
- Browser caches the resolved theme in `localStorage['focus-theme-state']` and
  the CSS bundle is served with an ETag. "It didn't change" is usually a stale
  reload, not a bug — hard-reload before debugging.

---

## 6. Remaining work

Order matters: primitives first, then one surface per commit, each deleting the
legacy blocks it replaces in the *same* commit. A commit that adds rules without
deleting the old owner is how the last attempt went wrong.

0. **`primitives.css` — done.** Vocabulary written, absorbed tokens moved to
   `variables.css`, the three `:not()` ladders and the `.btn*` legacy family
   deleted, `--font-mono-ui`/`font-synthesis-weight` moved out of
   `instrument.css`. Grid audit 140/140, both schemes checked.
1. **Shell + both sidebars — done.** Markup re-clased to primitives, legacy
   sidebar skin deleted from `instrument.css`/`layout.css`/`components.css`,
   `surfaces/shell.css` added, `surfaces/sidebar.css` rewritten,
   `design.css` reduced to the composer. Ruler 141/141. Resolved map §2 #1, #2,
   #3, #4, #6, #12. Known leftover: `.btn-danger`/`.btn-create`/`.btn-hero` in
   the composer and the modals are now unstyled variants until their surface
   lands (they fall back to the neutral plate).
2. **Messages + composer** — `.frame`/`.well`/`.disclosure`/`.key`, delete
   `chat.css`, `input.css`, `surfaces/messages.css`'s legacy overlaps.
   Resolves #5, #10, #11.
3. **Modals + forms** — `.panel`/`.rail`/`.row`/`.field`/`.check`/`.switch`,
   delete the modal + form blocks from `instrument.css` and `components.css`.
   Resolves #7, #8, #9. Consistency here is free — it is composition now.
4. **Overlays** — toast/tooltip/lightbox/option picker on `.toast`/`.tooltip`/
   `.panel`, delete `animations.css`.
5. **Delete** `instrument.css`, `design.css`, `layout.css`, `chat.css`,
   `input.css`, `components.css`, `animations.css`. Then add
   `tests/frontend/test_css_ownership.py`: fail if any file outside
   `primitives.css` sets a look property (`background*`, `box-shadow`, `color`,
   `border*`, `font*`, `text-transform`, `letter-spacing`) on a selector whose
   subject is a primitive class, or contains `:not(`. That test is the gate that
   keeps this from rotting back.

Open decisions from the map (§4) are already called: D1 new `.check` shape;
D2 `.tag` for static markers (`.chip` stays toggle-only); D3 `.field[type=range]`;
D4 radio uses `.check`; D5 `.note` inline + `.tooltip` overlay (two things);
D6 prose is a scope in `surfaces/messages.css`; D7 `.pager` composite; D8 role
colour as a row *edge*; D9 `.grip` drawn, not `⋮⋮`; D10 one `.spinner`;
D11 `.frame` for raised panels; D12 `.field.ghost` / `.field.swatch`.

**Still open:** the preset-variables section flexes to fill the left pane, so a
short list leaves ~400px of empty chassis above TOOLS. Make the list a recessed
well so the space reads as an empty list, not a hole. Not started.

---

## 7. Traps

- **Don't rename** ids, `data-ui`, `data-action`, `hx-*`, or the state classes
  JS toggles (`hidden`, `active`, `processed`, `reasoning-open`, `drag-over`,
  `expanded`). JS is fully described by `data-ui`; classes are styling only.
- Tailwind utilities are in a layer and **lose** to unlayered `instrument.css`
  and `surfaces/*`. Adding `p-0` or `rounded-md` to fight a legacy rule does
  nothing; write the rule in the owning surface file.
- The pruner stores `offsetHeight`; changing message heights is fine, changing
  the DOM shape JS queries is not.
- Message markup is single-sourced. Editing `templates/macros.html` message
  macros requires regenerating `tests/frontend/fixtures/message-templates.html`
  or the fixture test fails (it renders the same Jinja template with the test's
  env — just do that).
- If delegating to agents: give them exclusive file ownership (the surfaces are
  split precisely so two agents never share a file), the token names they may
  use, and the ruler command as the acceptance gate. They cannot judge "does
  this look like FL" — the material is tokenised so they don't need to, but any
  agent that starts inventing shadows or px values is off-contract.

## 8. User's explicit preferences (learned the hard way)

- Compact chat list: one line per row, fixed 80px readout column carrying date
  over persona; persona must stay visible.
- No red washes on destructive controls; red in ink only.
- No corner/bracket motifs; no rounded cards.
- Everything aligned: hairlines on row boundaries (midway between values), no
  "floating" lines 4px below content.
- Message frames: heavier (current tuned values) rather than lighter.
- Alignment is non-negotiable; if something is 1–2px off it *will* be noticed.
- Separators are grooves (dark line + lit line under it), never a lone dark line
  — a lone one reads as a gap between separate plates.
- Row content gets interior padding; hairlines share edges across nesting levels.
  An indent belongs in `padding`, not in the row's box.
- Carets and separator dots are drawn (`.caret-mark`, a 2px square), never glyphs
  or icons — those sit on their own half-pixel and stop sharing a centre line
  with neighbouring type at 1x zoom.
