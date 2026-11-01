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

**B. New skin — in progress.** FL-Studio-ish pseudo-skeuomorphic language,
calibrated on the shell + messages. Commits `329409e` … `34d27b3`, then the
pass on the shell + both sidebars (`58bd82c` … `7433320`):

| commit | what |
|---|---|
| `58bd82c` | separators are grooves (`--hair-dark` + `--hair-lit`), not single black cuts; `--mat-lo` 28%→22% |
| `c041d40`, `ba69810` | the reasoning caret is drawn (`.caret-mark`), the `·` became a 2px square, one gutter on both sides |
| `ba69810` | toolbar keys take full text ink (muted ink on a white plate was invisible on light themes) |
| `cf78be5`, `7433320` | preset variables migrated to the new language (square LEDs, drawn carets, mono values, grooves); 153 lines of legacy sidebar-var skin deleted, which also killed the 1px `border-bottom` dividers |

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

## 3. CSS architecture (transitional)

```
variables.css   grid + material tokens            (single source)
tokens.css      Tailwind @theme (fonts/radius)
base.css        reset
layout/chat/input/components/animations   ← LEGACY, layered
instrument.css  ← LEGACY, unlayered, still wins over the above
design.css      NEW: primitives + calibrated left sidebar & composer
surfaces/sidebar.css    NEW: right sidebar, chat list, pager, composer chrome
surfaces/messages.css   NEW: message frame/screen/rail/reasoning/tool cards
```

Import order in `static/tailwind-input.css` puts `design.css` and
`surfaces/*` last, unlayered — so they beat legacy rules without touching them.
`instrument.css` (1976 lines and falling) is still the old skin underneath and
must be deleted once every surface is migrated. Do not add new rules to the
legacy files.

`design.css` also owns the two primitives both sidebars and messages need:
`.caret-mark` (a drawn caret — integer geometry, so it cannot lose an edge to
antialiasing at 1x the way a 12px icon's diagonal does) and the `--hair-groove`
token pair. Use them rather than an `icon_chevron_right(12)` or a lone dark
line.

When a surface is migrated: write its rules in its `surfaces/*.css`, delete the
matching legacy block, and add the surface's boxes to the ruler.

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

**Shell + both sidebars: done** — except one open question: the preset-variables
section flexes to fill the pane, so a short variable list leaves ~400px of empty
chassis above TOOLS. The suggested fix is to make that list a recessed well
(like the status panel) so the space reads as an empty list instead of a hole.
Not started; needs a call.

**Surfaces still on the old skin** (priority order):

1. **Modals** — `modal_shell`, headers, tab bars (`partials/chat/modals.html`,
   `partials/modals/sampler.html`), advanced list rows (tools, extensions,
   regex, structured, backups). New file: `static/css/surfaces/modals.css`.
   Legacy blocks: `instrument.css` modal sections, `components.css` modal/tab.
2. **Form modals** — providers, sampler, arranger, theme, edit-entity, itemizer,
   summary, text-expander, option picker. New file: `surfaces/forms.css`. These
   consume the most primitives; if a primitive is missing, add it to
   `design.css` once and use it everywhere.
3. **Pickers, toasts, tooltips, lightbox** — `option-picker.html`,
   `animations.css` toast blocks, `#hint-tooltip`, `#lightbox`.
4. **Remaining flat keys** — sidebar collapse chevrons, pager arrows at rest,
   lightbox close, media-thumb ×. One class each.

**Then:**
- Delete `instrument.css` and remove the now-dead blocks from
  `layout/chat/input/components.css`; one owner per selector.
- Dead-code sweep (unused classes / `window._*` / api-paths).
- Optional debt, deliberately deferred: form read/write has ~15 implementations
  and 102 hardcoded IDs (`providers.js` names only 25 of the 32 `prov-form-*`
  fields it renders). It does not block the skin; do it after, once the final
  control set is known.
- Registry bypasses (87 raw `fetch` vs 31 `hx*`, `Refresh` bypasses) untouched.

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
