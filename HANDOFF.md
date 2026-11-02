# Handoff — UI overhaul

Branch `refactor/consolidate-ui`, off `master` (d7b89ad). Last commit `4239045`.
1416 backend tests + 269 frontend tests green; grid audit 91/91 on the current
(short) chat, 141/141 when the full sidebar/message surface is present.

Read this, then `static/css/primitives.css` (the closed vocabulary), then
`PRIMITIVE-MAP.md` (the class audit that produced it). The CSS import order in
`static/tailwind-input.css` is the load-bearing part of the architecture:
legacy → surfaces → primitives, so primitives win every collision.

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

**B. New skin — rebuilt primitive-first.** The first skin pass (shell, messages,
sidebars) was abandoned because it produced *overrides* instead of replacements:
1642 new lines against 153 deleted, 37 two-owner selectors, and `:not()` ladders
that made one class mean two things. `PRIMITIVE-MAP.md` maps all 243 legacy
classes onto one closed vocabulary (57 layout-only, 12 decisions, 25 protected
JS hooks).

| step | state | what |
|---|---|---|
| 0 | done | `PRIMITIVE-MAP.md` audit |
| — | done | `primitives.css` written, tokens repaired, `:not()` ladders + `.btn*` legacy family deleted (`2796b9d`) |
| 1 | done | shell + both sidebars (`70221c5`), `surfaces/shell.css` added |
| 2 | done | messages + composer (`2b1feb5`), `chat.css` `input.css` `design.css` deleted |
| — | done | polish rounds: grip LED, well rows, disclosure plates, reasoning block, prose metrics, composer (`c201e7b` … `4239045`) |
| 3 | **next** | modals + forms |
| 4 | todo | overlays (toasts, tooltips, lightbox, option picker) |
| 5 | todo | delete the last legacy files + add the ownership guard test |

---

## 2. The primitive contract

Closed set — shapes are fixed, modifiers compose:

```
controls   .btn .key .nav .link .chip .tab .pager
inputs     .field .check .switch
structure  .rail .row .well .frame .panel .card .divider .disclosure .grip
feedback   .toast .tooltip .spinner .empty .note .tag .avatar
```

- Intents: `.primary .create .danger .warning .success`. Sizes: `.sm .lg .xl`,
  plus `.raised` on `.key` (a key that needs a plate of its own inside a well).
- State is class-driven exactly as JS toggles it: `.active .disabled .expanded
  .hidden .drag-over .copied .favorite-active .on`.
- **Intent is ink + edge, or a tinted plate** (`.create`/`.toast-success`), never
  a wash over a raised control. `.key.primary` is a solid accent key with a
  lit-from-above gradient; `.key.primary.danger` swaps the hue for stop.
- **Fill is the state in exactly one place**: `.grip` (the preset-variable drag
  handle) — grey = no choice set, accent = set. The user chose the solid bar over
  engraved lines; do not "fix" it back.
- **A surface may set layout on its own container; it may not restyle a
  primitive.** If a surface needs a different look, the primitive is wrong. Named
  slots exist for exactly this: `.disclosure-title` / `.disclosure-meta`,
  `.row-title` / `.row-meta` / `.row-label` / `.row-value` / `.row-actions`.
  Never select on child position inside a primitive.
- Hairlines are `inset box-shadow`, never `border`. Geometry is multiples of
  `--u` (4px). No `:not()` ladders, no surface-scoped overrides of a primitive.

### Tokens (`variables.css`)

Grid: `--u` 4, `--inset` 12, `--gutter` 8, `--rail-h` 24, `--row-h` 28,
`--control-h{,-sm,-lg}` 28/24/32, `--hair-w` 1, `--radius-panel` 0,
`--radius-control` 2.

Material: `--mat-raise`, `--mat-raise-fill`, `--mat-inset`, `--mat-well`,
`--mat-brush`, `--mat-hi/shade/lo/edge/glow`, `--hair-dark`/`--hair-lit`,
`--hair-groove`.

Ink/tint: `--ink-1/2`, `--hair`, `--hair-strong`, `--engrave`, `--tint-1/2/3`,
`--edge`, `--danger-*`, `--success-*`.

Font metrics: `--prose-ink-lead: 7px`, `--prose-ink-trail: 4px` — distance
between a prose line box's edge and its ink at Ronzino 14/24. They are
subtracted from `.message-body > .message-content`'s block margins so prose reads
at the same rhythm as a plate beside it. **Re-measure if the body face or rhythm
changes.**

---

## 3. CSS architecture

```
variables.css   grid + material + ink/tint + font metrics   (single source)
tokens.css      Tailwind @theme (fonts/radius/shadows)
base.css        reset + the one scrollbar rule
primitives.css  THE vocabulary — the only file that styles a control
surfaces/shell.css     chassis, pane widths, collapsed grips
surfaces/sidebar.css   sections, preset selector/menu, variables, tools, status, chat rows, footer
surfaces/messages.css  chat column, message frame/rail/screen, prose scope, composer
```

Import order: `tailwindcss → variables → tokens → base → layout → components →
animations → instrument → surfaces/shell → surfaces/sidebar → surfaces/messages →
primitives`. Surfaces are unlayered and come after legacy; primitives come last.

**Still legacy** (target of steps 3–5): `instrument.css` (1248 — modals + forms
only), `components.css` (645 — form/control leftovers, modal extras),
`animations.css` (193 — toasts + keyframes), `layout.css` (50 — element-level
form defaults; the only file left in `@layer components`).

---

## 4. Verification

```bash
fuser -k 8010/tcp; uv run python main.py --host 127.0.0.1 --port 8010

# after any CSS change — tailwind.css is a generated, gitignored artifact
./bin/tailwindcss-linux-x64 -i static/tailwind-input.css -o static/tailwind.css

node tests/frontend/grid-audit.js http://127.0.0.1:8010   # the ruler
uv run pytest tests/ -q
uv run pytest tests/frontend -q --no-cov -p no:cacheprovider
```

`grid-audit.js` measures the live app in Chrome: multiples of 4, sibling rows on
one top/height, pane insets, left/right rail baselines, tiles, status rows, var
groups/options, chat rows (against their scroll lane), pager, message frames on
the 800px column, screen inset 8, composer on the message column. **Add
selectors for every new surface** — a check that is not in the file does not
exist. It now *skips* checks whose surface is absent (empty chat, no preset
variables) instead of crashing; keep that property.

Screenshot both schemes after any visual change. Playwright is installed
(`chromium.launch({ channel: 'chrome' })`); apply the CSS build first, then
hard-reload — the bundle is served with an ETag.

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

## 6. Remaining work

3. **Modals + forms.** Re-class `partials/modal-shell.html`, `partials/chat/modals.html`,
   `partials/modals/*` to `.panel`/`.rail`/`.row`/`.field`/`.check`/`.switch`/`.btn`;
   write `surfaces/modals.css` + `surfaces/forms.css`; delete the matching blocks
   from `instrument.css` and `components.css`. Known leftovers to fix here: the
   edit-message modal's textarea still carries legacy `.edit-block-ta` styling on
   top of `.field`; `.btn-edit`, `.btn-icon`, `.btn-hero`, `.slot-btn`, `.btn-tag`,
   `.tab-btn`, `.tree-child`, `.key-row`, `.secret-item` are all still legacy.
   Resolves map §2 #7, #8, #9 — form modals are where the consistency payoff lands.
4. **Overlays.** `.toast` (intent = tinted plate + ink, already in primitives),
   `#hint-tooltip` → `.tooltip`, `#lightbox` → `.panel`, the option picker,
   confirm. Delete `animations.css`'s component blocks, keep the keyframes.
5. **Delete + guard.** `rm` `instrument.css`, `components.css`, `animations.css`,
   `layout.css` (move the element-level form defaults into `base.css` or drop
   them). Then add `tests/frontend/test_css_ownership.py`: fail if any file
   outside `primitives.css` sets a look property (`background*`, `box-shadow`,
   `color`, `border*`, `font*`, `text-transform`, `letter-spacing`) on a selector
   whose subject is a primitive class, or contains `:not(`. That test is the gate
   that stops the old two-owner pattern from returning.

Deferred debt, deliberately: form read/write has ~15 implementations and 102
hardcoded IDs; registry bypasses (87 raw `fetch` vs 31 `hx*`) untouched.

---

## 7. Traps learned the hard way

- **`.message` must carry `.frame`.** The look comes from the primitive; drop the
  class and messages render as bare prose. This happened once and cost a round.
- **The pre-answer reasoning block has no head.** Its toggle lives on the rail
  (`message_meta(..., show_reasoning)`); the index-0 block is a headless
  `.disclosure` hidden with `display: none` while its content is `.hidden`, so it
  leaves no strip and no gap. `toggleReasoning` unhides the content; every
  `<details>` block carries its own `summary`. `ensureReasoningToggleButton`
  inserts into `message-meta`, never into the block.
- **Disclosures need a ring.** A fill alone disappears on themes where
  `--surface` and `--mat-well` are the same value; `.disclosure` carries
  `inset 0 0 0 1px var(--hair)` and that is what makes the body read as enclosed.
- **Only the rail's own caret turns.** `.message.reasoning-open .message-meta
  .reasoning-chevron` — an unscoped rule flipped every disclosure in the message.
- **`textarea` needs `rows="1"`.** Without it, `height: auto` falls back to the
  UA's two-row intrinsic height and `resizeTextarea` makes the composer jump on
  the first keystroke. Height is driven by `scrollHeight` vs the CSS
  `max-height`; never reintroduce a constant like the old `44px`.
- **Chat rows are measured against their scroll lane**, not the pane: the
  scrollbar gutter makes `pane width - 2*inset` impossible.
- **The composer floats**: `.input-bar` has 10u (40px) bottom padding, putting the
  composer's centre at 936 vs the status readout's midline 920. The status panel
  grows by 12px per extra row (cache/key rows), so that alignment drifts.
- **Tailwind utilities lose** to unlayered surface/primitives rules. Adding `p-0`
  or `rounded-md` to fight them does nothing; write the rule in the owning file —
  and for look properties, in `primitives.css` behind a modifier.
- **Message markup is single-sourced.** Editing the message macros means
  regenerating `tests/frontend/fixtures/message-templates.html` (render
  `chat/message-templates.html` with a plain Jinja env; the test compares text).
- **The pruner stores `offsetHeight`**; message heights may change, the DOM shape
  JS queries may not.
- Don't rename `id`, `data-ui`, `data-action`, `hx-*`, or the state classes JS
  toggles (`hidden active disabled expanded details drag-over processed ready
  copied favorite-active reasoning-open message-placeholder toast*`).

---

## 8. User's explicit preferences (learned the hard way)

- Compact chat list: one line per row, fixed 80px readout column (date over
  persona); persona must stay visible.
- No red washes on destructive controls in general — but **intent plates**
  (create, toast success/error, primary key) carry their hue across the whole
  surface, because a 1px edge does not read as "this failed" from across the
  screen.
- No corner/bracket motifs, no rounded cards. Controls get `--radius-control` (2),
  panels stay square.
- Everything aligned; if something is 1–2px off it *will* be noticed. Gaps next to
  prose are compensated by font metrics, not eyeballed.
- Separators are grooves (dark line + lit line under it), never a lone dark line.
- Row content gets interior padding; an indent belongs in `padding`, not in the
  row's box. Rows inside a `.well` paint no groove at all — the well is the frame.
- Carets and separator dots are drawn (`.caret-mark`, a 2px square), never glyphs.
- Message frames: heavier rather than lighter. The reasoning toggle stays next to
  the model name. Disclosures are plates, not loose ruled prose.
- Composer: 14px body, floating clear of the floor, and it must not change size
  on the first keystroke.
