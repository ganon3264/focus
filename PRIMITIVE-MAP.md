# PRIMITIVE-MAP.md

Audit of the 243 legacy classes in `/tmp/legacy-classes.txt` against the closed primitive vocabulary (HANDOFF.md §2, `design.css`).

Abbreviations: `comp`=static/css/components.css `chat`=static/css/chat.css `inp`=static/css/input.css `lay`=static/css/layout.css `anim`=static/css/animations.css `inst`=static/css/instrument.css `des`=static/css/design.css `sb`=static/css/surfaces/sidebar.css `ms`=static/css/surfaces/messages.css `tw`=static/tailwind-input.css.

Cascade: `comp/chat/inp/lay/anim` are `@layer components` (lose to unlayered); `inst`, `des`, `sb`, `ms` are unlayered, imported in that order (`tw:1-13`) → **`ms` > `sb` > `des` > `inst` > layered**, ties broken by specificity.

## §0 Summary

| bucket | count |
|---|---|
| classes examined | **243** |
| mapped to a primitive | **153** |
| layout-only (geometry, surface-owned) | **57** |
| needs-decision (§4) | **33** (inside 12 decisions) |
| protected / keeps its name (§5) | **25** (subset of the above) |

## §1 Mapping table

`used in` = occurrences in `templates/` + `partials/` + `static/js/` (markup + authored strings), representative site.

### 1.1 `.btn` — labelled control (28h / `.sm` 24 / `.lg` 32)

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `btn` | comp:131,146,156; inp:97; inst:329,333,344,778,791,898,1403,1406,1415,1759,1952; sb:22,42,47,53,347,365,370,376,429; des:— | 117 html + 86 js @ templates/macros.html:108 | flat, hairline, 12px sans, no shadow | `.btn` |
| `btn-sm` | comp:194 | 52 @ macros.html:108 | compressed padding, 0.8rem | `.btn.sm` |
| `btn-compact` | comp:199 | 4 @ partials/modals/greeting-section.html:16 | minimal padding, min-width 0 | `.btn.sm` |
| `btn-hero` | comp:209; inst:350 | 2 @ partials/chat/center-pane.html:62 | large padding, pill radius, 13px | `.btn.lg` |
| `btn-primary` | comp:149,152; inst:70,401,407; sb:74 | 17 @ templates/base.html:248 | accent tint fill + accent hairline | `.btn.primary` |
| `btn-secondary` | comp:166,171,174; inst:312,314,322 | 59 @ macros.html:108 | surface fill, 1px border, `shadow-sm`(=none) | `.btn` (neutral default) |
| `btn-create` | inst:413,421; sb:58,64,70 | 16 @ partials/chat/center-pane.html:62 | green tint + green edge, square | `.btn.create` |
| `btn-danger` | inst:495,503,504 | 16 @ partials/chat/center-pane.html:40 | no chrome, danger ink, tint on hover | `.btn.danger` |
| `btn-media-add` | comp:214; inst:1798,1803 | 2 @ partials/modals/edit-entity.html:73 | dashed green add tile, 48h | `.key.lg` + `.create` |
| `external-media-btn` | chat:267,276; ms:444,453 | 1 js @ messages/message-renderer.js:55 | small hairline button in a slot | `.btn.sm` |

### 1.2 `.key` — square icon control

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `action-btn` | inp:40,50,56,61,67,74,84,93; inst:586,590,1276,1283,1284; ms:241,251,256,262,266 | 10 @ partials/chat/message-toolbar.html:4 | transparent 28px key; raised plate in rail | `.key` |
| `action-icon` | comp:462,472,477,481; inp:42,52,94; inst:139,140,149,150,387,1275,1282,1763,1774; des:68,69,82,83,167,278,289,293 | 9 @ partials/chat/right-pane.html:9 | filled `surface-3` square, 16-24px | `.key` |
| `slim` | comp:472 | 5 @ partials/modals/structured-item.html:33 | 18px key modifier | `.key.sm` |
| `btn-icon` | comp:203; inst:1578 | 3 @ partials/modals/edit-entity.html:121 | 36×36 square icon-only | `.key.lg` |
| `btn-edit` | inst:1262,1269,1764,1779 | 3 @ partials/modals/character-card.html:34 | 24px hairline-framed icon | `.key` |
| `attach-btn` | inp:41,51,57,62,68,88,95; inst:687,694; des:449,458 | 1 @ partials/chat/center-pane.html:23 | 44px hairline square; now bare 32 | `.key.lg` |
| `send-btn` | inp:43,53,58,63,69,96,154,159,170; inst:700,707,712,718; des:464,479,483 | 2 @ partials/chat/center-pane.html:27 | accent-filled square key | `.key.lg.primary` |
| `stop-btn` | inp:164,167,171; inst:712,718 | 1 @ partials/chat/center-pane.html:30 | danger ink on the send key | `.key.lg.danger` |
| `expand-btn` | comp:105,119,122,125; inp:44 | 3 @ partials/modals/edit-entity.html:103 | 28px key floating in textarea corner | `.key.sm` |
| `sidebar-delete-btn` | lay:195,202,203; inst:475,482; sb:230,251,255 | 1 @ partials/chat/chat-list.html:26 | hover-revealed danger key, raised | `.key.sm.danger` |
| `preset-item-action` | inst:252,267,272,276,1762,1769 | 5 @ partials/presets/preset-selector.html:31 | 24px bare icon key, tint on hover | `.key.sm` |
| `key-nav` | lay:145,155,167 | 2 @ partials/chat/sidebar/status-section.html:11 | bare chevron, no chrome | `.key.sm` |
| `copy-btn` | chat:223,238,241,246; ms:416,427 | 2 js @ messages/message-renderer.js:127 | 20px floating key on `<pre>` | `.key.sm` |
| `media-thumb-close` | comp:510 | 1 @ templates/macros.html:459 | × key, Tailwind-positioned | `.key.sm` (protected name) |
| `fav-star` | comp:633,639-643; ms:178,184 | 6 @ partials/chat/message-toolbar.html:65 | star glyph toggle, amber when on | `.key` + `favorite-active` |
| `fav-star-outline` | comp:639,642 | 3 @ partials/chat/message-toolbar.html:66 | idle star shown | `.key` sub-glyph |
| `fav-star-filled` | comp:640,643 | 4 @ partials/chat/message-toolbar.html:67 | active star shown | `.key` sub-glyph |
| `toast-btn` | anim:184,199 | 1 js @ ui/notifications.js:128 | 24px bare icon key | `.key.sm` (protected name) |
| `left-tab` | lay:285,300; inst:513 | 1 @ partials/chat/left-pane.html:13 | 40px vertical collapse strip | `.key` (collapse grip) |
| `right-tab` | lay:264,279; inst:512 | 1 @ partials/chat/right-pane.html:33 | 40px vertical collapse strip | `.key` (collapse grip) |

### 1.3 `.nav` / `.chip` / `.tab` / `.link`

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `tool-tile` | comp:754,761,767,772,773; inst:295,305,306,314,322,331,333,344,350; des:338,356,361,367 | 8 @ partials/chat/sidebar/tools-section.html:7 | 2-col raised bevel tile, icon+label, 32h | `.nav` |
| `btn-tag` | comp:573; inst:1731,1742,1747,1753 | 28 @ partials/modals/sampler.html:58 | small bordered pill, accent when on | `.chip` |
| `slot-btn` | comp:664,676; inst:1242,1252,1377,1729 | 2 @ partials/modals/theme.html:37 | 44×24 bordered mini button | `.chip` |
| `tab-btn` | comp:622; inst:1214,1222 | 1 @ templates/macros.html:249 | text tab, 2px accent underline | `.tab` |
| `btn-link` | comp:178,189,190; inst:333,344,350,1765 | 3 @ partials/modals/provider-create.html:38 | bare 11-12px text action | `.link` |
| `summary-boundary-btn` | chat:115,129; ms:638,647 | 1 @ partials/chat/message.html:88 | mono caps text action | `.link` |
| `summary-boundary-edit` | chat:132; ms:651 | 1 @ partials/chat/message.html:90 | same, uncaps, full opacity | `.link` |
| `reasoning-toggle-btn` | chat:345; ms:126,132,154 | 2 @ templates/macros.html:484 | meta-row text toggle + caret | `.link` + `.disclosure` caret |

### 1.4 switch / intent / state hooks

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `arranger-toggle` | comp:243,251; inst:1188,1194,1203,1208 | 1 @ templates/macros.html:198 | 32×18 pill, sliding square knob | `.switch` |
| `is-create` | comp:158,162; inst:1762,1763,1764,1765,1769,1774,1779,1785,1789,1794; des:323,327 | 6 @ partials/chat/sidebar/preset-variables-section.html:6 | green ink intent modifier | intent `.create` (name kept) |
| `danger` | inst:272,276,1275,1282; des:293 | 6 @ partials/modals/structured-item.html:33 | danger ink modifier | intent `.danger` (name kept) |
| `text-danger` | inst:1276,1283,1284; ms:262,266 | 2 @ partials/chat/message-toolbar.html:95 | danger ink on a toolbar key | intent `.danger` (protected name) |
| `active` | comp:274,284,481; lay:190,248,257; inst:452,465,843,847,848,1203,1208,1222,1747; des:261,273; sb:149,192,226,336,341 | 70 html + 42 js @ templates/macros.html:97 | selected/on state, 5 recipes | `.active` state on every primitive (protected) |
| `disabled` | comp:345 | 17 html @ partials/chat/chat-pager.html:8 | 0.6 opacity + grayscale | `.disabled` state (protected) |
| `expanded` | inst:1844,1923 | 13 @ partials/modals/itemizer.html:29 (+15 js) | rotates caret, opens row | `.expanded` on `.disclosure` (protected) |
| `hidden` | tw:16-18 (`!important`); inp:170,171 | 67 html @ macros.html:57 (+45 js) | `display:none !important` | `.hidden` utility (protected) |
| `processed` | chat:187,320 | 3 @ templates/macros.html:525 (+9 js) | markdown-rendered gate | `.processed` on prose (protected) |
| `ready` | chat:24 | 3 js @ messages/message-renderer.js:171 | opacity fade-in gate on list | `.ready` (protected) |
| `drag-over` | comp:353; inst:941 | 3 js @ ui/media-utils.js:82 | dashed accent outline + tint | `.drag-over` state on `.well` (protected) |
| `favorite-active` | comp:641,642,643; ms:184 | 4 @ partials/chat/message-toolbar.html:65 | amber flag state | `.favorite-active` (protected) |
| `copied` | chat:246 | 2 js @ messages/message-renderer.js:154 | opaque accent copy key | `.copied` (protected) |
| `checkbox` | comp:36,50,58,61,65; inst:921 | 7 @ partials/chat/message.html:8 | 16px square, mask tick | `DECISION #1` |
| `delete-mode-checkbox` | chat:103; ms:286 | 2 @ partials/chat/message.html:6 | absolutely-placed tick box | `DECISION #1` |
| `radio-switch` | comp:259,271,274,277,284; des:243,254,261,273 | 2 @ partials/presets/var-group.html:25 | 18px round radio, accent ring | `DECISION #4` |
| `radio-inner` | comp:277,284; des:254,261 | 1 @ partials/presets/var-group.html:28 | 8px round dot | `DECISION #4` |
| `styled-slider` | comp:681,690,699 | 1 @ templates/macros.html:217 | 6px ranged track, square thumb | `DECISION #3` |
| `gen-pulse` | anim:62 | 1 js @ messages/generation-ui.js:53 | 6×14 accent bar, pulsing | `DECISION #10` (protected) |
| `message-spinner` | chat:35,49,58,71,81; ms:668,677,681,689 | 1 @ partials/chat/message-templates.html:15 | light tracing the avatar bezel | `DECISION #10` |

### 1.5 `.field`

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `form-control` | comp:13,25; inst:69,156,169,170,1062,1405,1410,1861; des:90,105,106 | 56 @ templates/macros.html:213 | `surface-2` box, 1px border, glow focus | `.field` |
| `form-control-xs` | comp:30 | 4 @ templates/macros.html:276 | 56×20 mini input | `.field.sm` |
| `sampler-input` | comp:707,714,715 | 2 @ templates/macros.html:213 | 64px centred numeric input | `.field.sm` |
| `edit-block-ta` | comp:79,92 | 1 @ partials/modals/edit-message.html:4 (+4 js) | bordered textarea, own skin | `.field` (protected name) |
| `textarea-wrapper` | comp:98,119,122; inst:1088,1089,1133 | 2 @ partials/modals/edit-entity.html:93 | relative flex shell for a textarea | `.field` wrapper (protected name) |
| `key-row` | comp:385,391 | 1 @ partials/modals/provider-create.html:45 | bordered surface-2 row | `.row` |
| `secret-item` | comp:744,745 | 1 @ partials/modals/providers.html:109 | bordered row, hover accent edge | `.row` |
| `model-item` | comp:741,742 | 1 @ partials/modals/providers.html:66 | transparent row, hover fill | `.row` |
| `tree-child` | comp:721,727,735 | 5 @ partials/modals/sampler.html:49 | 12px-indented flex row + dot | `.row` (indent in padding) |
| `arranger-input` | comp:437,448,449,452; inst:1539 | 6 @ partials/modals/structured-item.html:21 | borderless inline name input | `DECISION #12` |
| `theme-color-input` | inst:1435,1445,1449,1450 | 1 @ partials/modals/theme.html:98 | framed native colour swatch | `DECISION #12` |
| `block-preview` | comp:547,560 | 3 @ partials/presets/prompt-block.html:84 | clickable truncated preview, hover fill | `DECISION #5` |

### 1.6 `.row` + `.row-meta` / `.row-actions`

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `sidebar-item` | lay:172,186,190,195,202,203; inst:432,442,446,452,459,465,469,475,482; sb:123,140,144,149,155,167,168,174,179,183,192,196,213,217,226,230,246,247,251,255 | 3 @ partials/chat/chat-list.html:14 | 32h row, hair groove, absolute key | `.row` |
| `entity-list` | inst:819 | 3 @ partials/modals/providers.html:18 | 2-column, column-major flow | `layout-only: surfaces/forms.css` |
| `entity-name` | inst:848,868 | 3 @ partials/modals/character-card.html:17 | 13px medium truncated | `.row` title |
| `entity-meta` | inst:877 | 3 @ partials/modals/character-card.html:18 | 10px mono muted | `.row-meta` |
| `entity-side` | inst:888 | 1 @ partials/modals/providers.html:25 | 10px mono right readout | `.row-meta` |
| `entity-actions` | inst:897,898 | 3 @ partials/modals/character-card.html:32 | 26px key cluster | `.row-actions` |
| `theme-row` | inst:1319,1332,1336,1340,1345,1349,1377 | 1 @ partials/modals/theme.html:17 | flat row, accent left edge selected | `.row` |
| `theme-name` | inst:1349,1366 | 1 @ partials/modals/theme.html:35 | 13px medium truncated | `.row` title |
| `theme-swatches` | inst:1353 | 1 @ partials/modals/theme.html:21 | inline swatch strip | `.row-meta` |
| `backup-row` | inst:1141,1150 | 1 js @ features/backup-manager.js:89 | hairline data row | `.row` |
| `backup-row-date` | inst:1162 | 1 js @ features/backup-manager.js:91 | 11px mono date | `.row` title |
| `backup-row-size` | inst:1172 | 1 js @ features/backup-manager.js:94 | 10px mono size | `.row-meta` |
| `backup-row-actions` | inst:1179 | 1 js @ features/backup-manager.js:98 | key cluster | `.row-actions` |
| `backup-row-main` | inst:1154 | 1 js @ features/backup-manager.js:90 | flex column main col | `layout-only: surfaces/forms.css` |
| `dropdown-item` | comp:229,233,236; inst:215,222,287 | 10 @ templates/macros.html:72 | menu row, hover fill | `.row` |
| `preset-menu-item` | inst:226,231,235,247,248 | 1 @ partials/presets/preset-selector.html:49 | row, accent edge when selected | `.row` |
| `preset-item-name` | inst:235 | 1 @ partials/presets/preset-selector.html:57 | 13px truncated name | `.row` title |
| `preset-item-actions` | inst:240,247,248 | 1 @ partials/presets/preset-selector.html:58 | hover-revealed key cluster | `.row-actions` |
| `preset-menu-head-actions` | inst:201 | 1 @ partials/presets/preset-selector.html:30 | icon cluster | `.row-actions` (rail trailing) |
| `arranger-actions` | comp:456; des:186,203,208,216,225,226 | 4 @ partials/modals/structured-item.html:29 | right-aligned icon cluster | `.row-actions` |
| `arranger-item` | comp:337,341,345,349; inst:1465,1475,1476,1480,1485,1489,1494,1498,1503,1509,1514,1519 | 15 @ templates/macros.html:46 | flat row, 2px role left edge | `.row` (+ role edge, #8) |
| `var-group-container` | comp:299,514,518; des:135,145,153,161,167,168,176,186,203,208,216,225 | 2 @ partials/presets/var-group.html:4 | engraved group row with LED | `.row` |
| `var-group-name` | comp:314; des:191,204 | 1 @ partials/presets/var-group.html:9 | 12px medium truncated | `.row` title |
| `var-option-item` | comp:305,310; des:136,146,237,243,254,261,265,273,278,289,293 | 2 @ partials/presets/var-group.html:24 | indented option row + radio | `.row` |
| `radio-add-row` | comp:158,162,287,293; inst:1785,1789,1794; des:297,309,313,323,327 | 1 @ partials/presets/var-group.html:35 | dashed adder row, green when create | `.row` + `.create` |
| `itemizer-item` | inst:1598,1606 | 1 @ partials/modals/itemizer.html:30 | role-edged flat row | `.row` |
| `itemizer-readout` | inst:1585 | 1 @ partials/modals/itemizer.html:6 | mono label with accent value | `.row-meta` |
| `itemizer-readout-value` | inst:1593 | 1 @ partials/modals/itemizer.html:7 | accent bold number | `.row-meta` value |
| `itemizer-tokens` | inst:1669 | 1 @ partials/modals/itemizer.html:40 | muted token count | `.row-meta` |
| `message-meta` | inst:556; ms:105,119,126,132,140 | 1 @ templates/macros.html:503 | 10px mono model readout | `.row-meta` |
| `ts-date` | inst:563; ms:200 | 1 @ partials/chat/message.html:40 | mono faint date | `.row-meta` |
| `ts-time` | inst:564; ms:201 | 1 @ partials/chat/message.html:41 | mono faint time | `.row-meta` |
| `meta-right` | inp:25,28,34; inst:563,564,569; ms:172,178,184,228,232 | 1 @ partials/chat/message.html:33 | date/index readouts, fade on hover | `.row-actions` |
| `toolbar` | chat:102; inp:4,18; inst:577,586,590; ms:218,236,237,241,251,256,262,266 | 3 @ partials/chat/message-toolbar.html:1 | floating key strip on hover | `.row-actions` (+ `.key` children) |
| `status-key-row` | lay:145,155,158,167,168 | 1 @ partials/chat/sidebar/status-section.html:8 | status row for key switcher | `.row` inside `.well` |
| `regex-item` | inst:1844 | 4 @ partials/modals/regex-list.html:15 | flat row, expands | `.row` + `.disclosure` |
| `structured-item` | inst:1923 | 4 @ partials/modals/structured-list.html:15 | flat row, expands | `.row` + `.disclosure` |
| `regex-label-row` | inst:1855 | 1 @ partials/modals/regex-item.html:127 | label + key inline | `layout-only: surfaces/forms.css` |
| `structured-label-row` | inst:1934 | 2 @ partials/modals/structured-item.html:45 | label + key inline | `layout-only: surfaces/forms.css` |
| `regex-preview` | inst:1861 | 1 @ partials/modals/regex-item.html:154 | field + button on one line | `layout-only: surfaces/forms.css` |
| `arranger-header` | comp:360; inst:1526; des:153 | 4 @ partials/modals/structured-item.html:8 | space-between title line | `layout-only: surfaces/forms.css` (row part) |
| `arranger-title-group` | comp:417; inst:1527,1531; des:161,167,176,187 | 6 @ partials/modals/structured-item.html:11 | caret + name flex group | `layout-only: surfaces/forms.css` |
| `arranger-body` | comp:522 | 4 @ partials/presets/prompt-block.html:75 | flex row, 8px gap | `layout-only: surfaces/forms.css` |
| `arranger-add-buttons` | comp:568 | 1 @ partials/presets/prompt-arranger.html:34 | wrapped add-button row | `layout-only: surfaces/forms.css` |
| `arranger-list` | comp:329; inst:1459 | 1 @ partials/presets/prompt-arranger.html:3 | scrolling column, gap 0 | `layout-only: surfaces/forms.css` |
| `regex-sortable` | inst:1832 | 2 @ partials/modals/regex-list.html:14 | flex column, gap 0 | `layout-only: surfaces/forms.css` |
| `structured-sortable` | inst:1911 | 2 @ partials/modals/structured-list.html:14 | flex column, gap 0 | `layout-only: surfaces/forms.css` |
| `regex-group` | inst:1810 | 2 @ partials/modals/regex-list.html:3 | group block, 1rem apart | `layout-only: surfaces/forms.css` |
| `structured-group` | inst:1889 | 2 @ partials/modals/structured-list.html:3 | group block, 1rem apart | `layout-only: surfaces/forms.css` |
| `itemizer-header-left` | inst:1655 | 1 @ partials/modals/itemizer.html:34 | flex gap 6 | `layout-only: surfaces/forms.css` |
| `itemizer-bar-actions` | inst:1569,1578 | 1 @ partials/modals/itemizer.html:5 | key cluster | `.row-actions` |
| `bg-role-system` | comp:514,518; inst:1480,1485 | 1 @ partials/presets/var-group.html:4 | accent tint + edge for system role | `DECISION #8` |
| `arranger-badge` | comp:423,432; inst:1545 | 1 @ partials/presets/prompt-block.html:45 | tiny uppercase status badge | `DECISION #2` |
| `badge-auto` | comp:432 | 1 @ partials/presets/prompt-block.html:45 | danger-tinted AUTO tag | `DECISION #2` |
| `key-badge` | lay:158,168 | 1 @ partials/chat/sidebar/status-section.html:12 | key icon + count readout | `DECISION #2` |
| `tree-dot` | comp:727 | 5 @ partials/modals/sampler.html:50 | 6px round bullet | `DECISION #2` |

### 1.7 `.rail` — section header (engraved label + trailing actions)

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `sidebar-title` | lay:117; inst:115,116,130,131,139,140,149,150,387,391,395,755; des:43,44,59,60,68,69,82,83 | 9 @ partials/chat/right-pane.html:8 | engraved caps label + trailing key, 24h | `.rail` |
| `preset-menu-head` | inst:182 | 1 @ partials/presets/preset-selector.html:28 | label + icon cluster, bottom hairline | `.rail` |
| `preset-menu-label` | inst:191 | 1 @ partials/presets/preset-selector.html:29 | 10px mono caps label | `.rail` label |
| `itemizer-bar` | inst:1554 | 1 @ partials/modals/itemizer.html:3 | hint + readout + key, bottom rule | `.rail` |
| `regex-group-header` | inst:1814 | 2 @ partials/modals/regex-list.html:4 | label + add key, bottom rule | `.rail` |
| `regex-group-title` | inst:1824 | 2 @ partials/modals/regex-list.html:5 | 11px mono caps group label | `.rail` label |
| `structured-group-header` | inst:1893 | 2 @ partials/modals/structured-list.html:4 | label + add key, bottom rule | `.rail` |
| `structured-group-title` | inst:1903 | 2 @ partials/modals/structured-list.html:5 | 11px mono caps group label | `.rail` label |
| `edit-entity-field-head` | inst:1094,1101 | 1 @ partials/modals/edit-entity.html:63 | label row with trailing key | `.rail` |

### 1.8 `.well` / `.card` / media

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `status-panel` | comp:321; inst:356,365,372; des:373,382,397,401,405 | 2 @ templates/chat.html:58 | recessed readout, hairline rows | `.well` |
| `input-wrapper` | inp:121; inst:677,683; des:417,426; sb:416 | 2 @ partials/chat/center-pane.html:21 | composer well, inset, focus ring | `.well` |
| `staging-area` | inp:116; sb:385 | 1 @ partials/chat/center-pane.html:18 | tray above composer, 40h | `.well` |
| `delete-toolbar` | inp:131; sb:442 | 1 @ partials/chat/center-pane.html:36 | well with danger ring | `.well` + `.danger` |
| `edit-msg-drop` | inst:934,941 | 1 @ partials/modals/edit-message.html:32 | dashed drop target, tint on drag | `.well` |
| `theme-swatch` | inst:1359 | 3 @ partials/modals/theme.html:23 | 12px bordered colour chip | `.well` (mini) |
| `structured-preview` | inst:1940,1948,1952 | 1 @ partials/modals/structured-item.html:73 | flex column label/field/key | `.well` |
| `structured-preview-out` | inst:1956,1965 | 1 @ partials/modals/structured-item.html:85 | mono pre-wrap output | `.well` readout |
| `structured-preview-error` | inst:1969 | 3 js @ features/structured-responses.js:205 | danger ink on the readout | `.well` + `.danger` (protected) |
| `regex-preview-out` | inst:1865,1875 | 1 @ partials/modals/regex-item.html:162 | mono pre-wrap output | `.well` readout |
| `regex-preview-error` | inst:1879 | 3 js @ features/regex-scripts.js:293 | danger ink on the readout | `.well` + `.danger` (protected) |
| `media-thumb` | comp:488,496 | 1 @ templates/macros.html:453 | 48px clipped square, 1px border | `.well` (protected name) |
| `media-thumb-audio` | comp:501 | 1 js @ ui/media-utils.js:20 | centred glyph on `surface-3` | `.well` inner |
| `tile-card` | inst:1230,1237 | 2 @ partials/modals/tools.html:74 | frameless thumbnail + data tile | `.card` |
| `edit-avatar-placeholder` | inst:1021 | 1 @ partials/modals/edit-entity.html:18 | big muted initial in the frame | `.avatar` placeholder state |
| `edit-avatar-overlay` | inst:1027,1041 | 1 @ partials/modals/edit-entity.html:19 | dark hover scrim with caption | `.avatar` overlay |
| `edit-msg-drop-empty` | inst:946 | 1 js @ messages/edit-message.js:154 | centred muted caption in a well | `DECISION #5` |
| `empty-text` | comp:564 | 3 @ partials/presets/prompt-block.html:90 | 50%-opacity placeholder text | `DECISION #5` |
| `modal-subhead` | inst:806 | 1 @ partials/modals/providers.html:5 | quiet instruction line under title | `DECISION #5` |
| `external-media-placeholder` | chat:252; ms:434 | 2 js @ messages/message-renderer.js:55 | dashed slot with a load key | `DECISION #5` |
| `external-media-label` | chat:264 | 1 js @ messages/message-renderer.js:55 | nowrap label inside the slot | `DECISION #5` |

### 1.9 `.disclosure` + carets

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `details` | chat:282,292,295,299,302,307,340; inst:596,608,616,621,632,633; ms:473,491,498,503,508,513,518,519,526,534 | 5 @ templates/macros.html:533 (+11 js) | native `<details>`, mono summary, sticky | `.disclosure` (protected name) |
| `reasoning-block` | chat:340; inst:632; ms:461,518 | 2 @ templates/macros.html:533 | disclosure, sticky header, ruled body | `.disclosure` (protected name) |
| `reasoning-content` | chat:313,320,323,329,332,335; inst:620; ms:543,556,560 | 2 @ templates/macros.html:538 | ruled, muted sub-body | `.disclosure` body |
| `tool-call` | inst:633; ms:519,526,534 | 1 @ templates/macros.html:567 | disclosure for a tool call | `.disclosure` |
| `tool-result-body` | chat:302,307; inst:621; ms:544,566,579 | 1 @ templates/macros.html:575 | mono pre output inside the body | `.disclosure` body |
| `tool-calls-section` | chat:174; ms:462 | 2 @ templates/macros.html:586 | top-ruled group of disclosures | `layout-only: surfaces/messages.css` |
| `tool-calls-stream` | chat:175; ms:463 | 1 @ partials/chat/message-templates.html:20 | same, streaming variant | `layout-only: surfaces/messages.css` |
| `itemizer-header` | inst:1625,1639,1643,1647,1651 | 1 @ partials/modals/itemizer.html:33 | clickable row header, chevron + tokens | `.disclosure` summary |
| `itemizer-body` | inst:1673 | 1 @ partials/modals/itemizer.html:44 | padded body under a rule | `.disclosure` body |
| `itemizer-reasoning` | inst:1702 | 1 @ partials/modals/itemizer.html:54 | left-ruled sub-block | `.disclosure` (nested) |
| `itemizer-reasoning-header` | inst:1707 | 1 @ partials/modals/itemizer.html:55 | mono caps clickable header | `.disclosure` summary |
| `itemizer-reasoning-text` | inst:1719 | 1 @ partials/modals/itemizer.html:59 | 11px muted pre-wrap | `.disclosure` body |
| `regex-body` | inst:1848 | 1 @ partials/modals/regex-item.html:43 | indented, padded body | `.disclosure` body |
| `structured-body` | inst:1927 | 1 @ partials/modals/structured-item.html:43 | indented, padded body | `.disclosure` body |
| `reasoning-sticky-pill` | inst:654; ms:159 | 1 @ partials/chat/center-pane.html:7 | blurred floating pill button | `.chip` (floating) |
| `chevron` | chat:295,299; ms:508,513 | 2 @ templates/macros.html:535 (+2 js) | 12px svg caret, rotates 90° | `.disclosure` caret (`.caret-mark`) |
| `itemizer-chevron` | inst:1662 | 1 @ partials/modals/itemizer.html:35 | 12px glyph box, rotates 90° | `.disclosure` caret |
| `regex-chevron` | inst:1838,1844 | 1 @ partials/modals/regex-item.html:18 | inline-flex glyph, rotates 90° | `.disclosure` caret |
| `structured-chevron` | inst:1917,1923 | 1 @ partials/modals/structured-item.html:18 | inline-flex glyph, rotates 90° | `.disclosure` caret |
| `arranger-handle` | comp:365,375,378; inst:1535 | 5 @ partials/modals/structured-item.html:9 | 12px `⋮⋮` text glyph, grab cursor | `DECISION #9` |
| `itemizer-hint` | inst:1564 | 1 @ partials/modals/itemizer.html:4 | 12px muted sentence | `DECISION #5` |
| `arranger-note` | comp:542 | 3 @ partials/presets/prompt-block.html:111 | italic faint explainer | `DECISION #5` |
| `hint-wrapper` | anim:73 | 1 @ templates/macros.html:468 | inline-flex tooltip anchor | `DECISION #5` |
| `hint-icon` | anim:79,91 | 2 @ templates/macros.html:469 | 16px round `?` glyph | `DECISION #5` |
| `hint-danger` | comp:657 | 3 @ partials/modals/sampler.html:240 | danger-coloured hint text | `DECISION #5` |
| `hint-warning` | comp:658 | 6 @ partials/modals/sampler.html:38 | amber-coloured hint text | `DECISION #5` |
| `hint-success` | comp:659 | 3 @ partials/modals/sampler.html:249 | green-coloured hint text | `DECISION #5` |

### 1.10 `.menu` / `.modal` / `.toast` / `.empty` / `.divider`

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `dropdown-panel` | comp:225; inst:281,287 | 5 @ templates/macros.html:68 | floating `surface-2` panel, drop shadow | `.menu` |
| `preset-menu` | inst:176,215,222 | 1 @ partials/presets/preset-selector.html:23 | floating panel, hairline rows | `.menu` |
| `preset-menu-list` | inst:206 | 1 @ partials/presets/preset-selector.html:47 | scroll lane with gutter | `layout-only: surfaces/sidebar.css` |
| `modal-overlay` | comp:593,602; inst:726 | 4 @ templates/base.html:207 (+2 js) | fixed grid scrim, heavy backdrop | `.modal` overlay |
| `modal-content` | comp:605; inst:732,755,914 | 1 @ partials/modal-shell.html:43 | 500px panel, `--radius-lg` | `.modal` panel |
| `modal-footer` | comp:617; inst:798 | 1 @ templates/base.html:246 | right-aligned button row, top rule | `.modal` footer |
| `toast-container` | anim:115 | 2 @ templates/base.html:198 | fixed top-centre stack | `.toast` stack |
| `toast` | anim:128 | 8 js @ messages/stream-events.js:101 | blurred rounded card, colour tint | `.toast` (protected name) |
| `toast-text` | anim:162,168 | 4 js @ ui/notifications.js:13 | flex-1 text; mono for errors | `.toast` text (protected name) |
| `toast-actions` | anim:178 | 1 js @ ui/notifications.js:125 | key cluster | `.toast` actions (protected name) |
| `toast-leave` | anim:144 | 1 js @ ui/notifications.js:62 | exit animation hook | `.toast` exit state (protected name) |
| `regex-empty` | inst:1883 | 3 @ partials/modals/regex-list.html:17 | centred caption, 0.75rem pad | `.empty` |
| `structured-empty` | inst:1973 | 3 @ partials/modals/structured-list.html:17 | identical to `regex-empty` | `.empty` |
| `sidebar-rule` | lay:139; inst:104; sb:84 | 1 @ partials/chat/right-pane.html:19 | empty marker div → 1px line | `.divider` |
| `summary-boundary` | chat:108; ms:631 | 1 @ partials/chat/message.html:87 | ruled boundary between eras | `.divider` |
| `chat-pager` | lay:222; sb:285 | 6 @ partials/chat/right-pane.html:26 | centred flex pager, 28h | `DECISION #7` |
| `chat-pager-btn` | lay:228,247,253; sb:293,311,317,323 | 2 @ partials/chat/chat-pager.html:6 | 28px bare arrow key | `DECISION #7` |

### 1.11 message frame parts

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `message` | chat:71,81,86; inst:532,540; ms:6,13,35,172,178,184,205,218,228,232,236,237,241,251,256,262,266,270,277,286,294,305,309,316,320,324,328,334,339,343,358,367,372,382,389,395,402,408,412,416,427,434,444,453,461,462,463,469,473,491,498,503,508,513,518,519,526,534,543,544,556,560,566,579,588,595,602,611,615,624,631,638,647,651,668,677,681,689 | 55 @ templates/macros.html:271 (+101 js) | raised frame + rail + recessed screen | `DECISION #11` |
| `msg` | inp:18,28 | 13 @ templates/macros.html:516 (+77 js) | legacy alias hook on the message div | `layout-only: surfaces/messages.css` (delete once `.message` is the hook) |
| `message-body` | chat:166; ms:8,294,469 | 2 @ templates/macros.html:521 (+4 js) | recessed screen well | `.well` |
| `message-author` | inst:550; ms:94 | 1 @ templates/macros.html:499 | 13px medium name | `layout-only: surfaces/messages.css` |
| `message-content` | chat:173,178,183; ms:309,316,320 | 1 @ templates/macros.html:526 (+4 js) | 14px/24px prose in the screen | `layout-only: surfaces/messages.css` |
| `markdown-content` | chat:183,187,190,193,196,199,207,218,238,320,356,364,369,374,380,383,386,391,392,393,394,395,396,402,403,404,405,406,407,408,414,415,420,425,428; ms:316,320,324,328,334,339,343,358,367,372,382,389,395,402,408,412 | 3 @ templates/macros.html:526 (+2 js) | 35-rule prose typography block | `DECISION #6` |
| `accent-quote` | chat:431 | 1 js @ messages/message-renderer.js:111 | accent-ink quote span | `DECISION #6` |
| `pl-stream` | chat:434; ms:305 | 6 @ templates/macros.html:526 | 3rem hanging indent (now 0) | `layout-only: surfaces/messages.css` |
| `message-list` | chat:13; inst:526 | 2 @ partials/chat/center-pane.html:12 (+11 js) | 800px column, 16px gap | `layout-only: surfaces/messages.css` |
| `message-placeholder` | chat:28 | 8 js @ messages/message-refresh.js:49 | JS-height pruned stub | `layout-only: surfaces/messages.css` (protected name) |
| `reasoning-sticky-host` | inst:643 | 1 @ partials/chat/center-pane.html:6 | zero-height sticky host | `layout-only: surfaces/messages.css` |
| `ext-icon` | comp:778,783 | 2 @ partials/chat/message-toolbar.html:55 | inline-flex svg slot | `layout-only: surfaces/modals.css` (icon slot) |

### 1.12 layout-only geometry (57)

| class | defined at | used in | current appearance | → replacement |
|---|---|---|---|---|
| `app-shell` | lay:52 | 1 @ templates/chat.html:10 | 100vh flex row, clipped | `layout-only: surfaces/shell.css` |
| `left-sidebar` | lay:59,69; inst:45,50,57,69,85,96,115,130,139,149,156,169,170,291,295,305,306,356,365,372,1785,1789,1794; des:16,28,35,43,59,68,82,90,105,106,131,135,136,145,146,153,161,167,168,176,185,191,202,208,216,224,233,237,243,254,261,265,273,278,289,293,297,309,313,323,327,332,338,356,361,367,373,382,397,401,405 | 1 @ partials/chat/left-pane.html:3 | 312px chassis, brush, edge shadow | `layout-only: surfaces/sidebar.css` |
| `right-sidebar` | lay:81,91; inst:65,70,86,97,104,116,131,140,150,380,387,391,395,428,432,442,446,452,459,465,469,475,482,487; des:17,24,29,44,60,69,83; sb:8,22,42,47,53,58,64,70,74,84,96,108,123,140,144,149,155,167,168,174,179,183,192,196,213,217,226,230,246,247,251,255 | 1 @ partials/chat/right-pane.html:3 | same chassis, mirrored edge | `layout-only: surfaces/sidebar.css` |
| `main-content` | lay:73 | 1 @ partials/chat/center-pane.html:3 | flex column centred pane | `layout-only: surfaces/shell.css` |
| `chat-center` | chat:3; inst:522 | 1 @ partials/chat/center-pane.html:5 (+3 js) | scroll column, bottom mask, 20px inset | `layout-only: surfaces/messages.css` |
| `sidebar-inner` | lay:96 | 2 @ partials/chat/right-pane.html:4 | fixed-width inner column | `layout-only: surfaces/sidebar.css` |
| `sidebar-section` | lay:106,113; inst:50,57,65,70,85,86,96,97; des:28,29,35; sb:8,22,42,47,53,58,64,70,74 | 5 @ partials/chat/right-pane.html:7 | pane section: inset + hairline | `layout-only: surfaces/sidebar.css` |
| `sidebar-footer` | lay:211; inst:110; sb:266,347,365,370,376 | 1 @ partials/chat/right-pane.html:25 | pinned footer, top rule | `layout-only: surfaces/sidebar.css` |
| `sidebar-list` | lay:128; inst:428; sb:96 | 1 @ partials/chat/right-pane.html:21 | flex column, gap 0 | `layout-only: surfaces/sidebar.css` |
| `sidebar-title-v` | lay:304 | 2 @ partials/chat/right-pane.html:34 | vertical-rl label for collapsed pane | `layout-only: surfaces/sidebar.css` |
| `tools-grid` | comp:749; inst:291; des:332 | 1 @ partials/chat/sidebar/tools-section.html:6 | 2-col grid, 8px gap | `layout-only: surfaces/sidebar.css` |
| `input-bar` | inp:102; inst:673 | 2 @ templates/base.html:277 | centred bottom bar, pointer-none | `layout-only: surfaces/sidebar.css` |
| `input-bar-content` | inp:109; sb:385 | 1 @ partials/chat/center-pane.html:17 | flex column, 8px gap | `layout-only: surfaces/sidebar.css` |
| `scroll-fade` | inst:85,86,96,97; base:39,42 | 22 @ templates/base.html:119 | scroll-gutter marker, JS edge mask | `layout-only: base.css` |
| `form-group` | comp:3,6; inst:1055,1062,1077,1129 | 48 @ templates/macros.html:203 | label + control stack | `layout-only: surfaces/forms.css` |
| `entity-main` | inst:866 | 3 @ partials/modals/character-card.html:16 | flex-1 min-width-0 column | `layout-only: surfaces/forms.css` |
| `entity-greeting` | inst:1084 | 1 @ partials/modals/greeting-section.html:8 | flex-1 field taking height | `layout-only: surfaces/forms.css` |
| `edit-entity-form` | inst:958 | 1 @ partials/modals/edit-entity.html:8 | flex column modal form | `layout-only: surfaces/forms.css` |
| `edit-entity-body` | inst:966,1115 | 1 @ partials/modals/edit-entity.html:13 | two-column body with rule | `layout-only: surfaces/forms.css` |
| `edit-entity-side` | inst:973,986,1120 | 1 @ partials/modals/edit-entity.html:14 | 320px card sidebar, hairline | `layout-only: surfaces/forms.css` |
| `edit-entity-main` | inst:1066,1077,1084,1088,1089,1129,1133 | 1 @ partials/modals/edit-entity.html:90 | flex column content column | `layout-only: surfaces/forms.css` |
| `edit-identity` | inst:991 | 1 @ partials/modals/edit-entity.html:15 | avatar + field flex row | `layout-only: surfaces/forms.css` |
| `edit-identity-fields` | inst:1045,1055,1062 | 1 @ partials/modals/edit-entity.html:23 | flex column stretched fields | `layout-only: surfaces/forms.css` |
| `theme-list` | inst:1311 | 1 @ partials/modals/theme.html:14 | scrolling column of rows | `layout-only: surfaces/forms.css` |
| `theme-modal-body` | inst:1293 | 1 @ partials/modals/theme.html:12 | two-column modal body | `layout-only: surfaces/forms.css` |
| `theme-modal-list-col` | inst:1300 | 1 @ partials/modals/theme.html:13 | 340px list column | `layout-only: surfaces/forms.css` |
| `theme-modal-editor` | inst:1386 | 1 @ partials/modals/theme.html:77 | scrolling editor column | `layout-only: surfaces/forms.css` |
| `theme-name-row` | inst:1397,1405,1406,1410,1415 | 1 @ partials/modals/theme.html:78 | field + button on one line | `layout-only: surfaces/forms.css` |
| `theme-color-grid` | inst:1419 | 1 @ partials/modals/theme.html:91 | 2-column swatch grid | `layout-only: surfaces/forms.css` |
| `theme-color-field` | inst:1425 | 1 @ partials/modals/theme.html:93 | label over swatch | `layout-only: surfaces/forms.css` |
| `theme-del-spacer` | inst:1381 | 1 @ partials/modals/theme.html:61 | 24px invisible spacer | `layout-only: surfaces/forms.css` |

Count check — §1.1 10 · §1.2 21 · §1.3 8 · §1.4 24 · §1.5 12 · §1.6 56 · §1.7 9 · §1.8 23 · §1.9 28 · §1.10 17 · §1.11 13 · §1.12 22 = **243**.

## §2 Inconsistency ledger (ranked by how often you see both at once)

1. **Raised tool/action tile vs flat button — the same "do a thing" role, three skins in one pane.** `.tool-tile` new bevel (`des:338`) vs `.sidebar-delete-btn` (`inst:475` bare key → `sb:230` raised) vs New Chat / Trash Bin `.btn` (old flat `inst:314`; footer variants raised `sb:22`, `sb:347`). Both sidebars are on screen at once. Merged: `.nav` for tiles, `.btn` for the two full-width actions, `.key` for icon sites.
2. **Selected state — one role, two class names, five recipes.** `.active` on `.entity-row` (`inst:843` accent fill + edge) vs `.is-selected` on `.preset-menu-item` (`inst:231`) and `.theme-row` (`inst:1336`) vs `.slot-active` (`inst:1252`) vs edge-only `.sidebar-item.active` (`sb:149`, ink wash + 2px inset line) vs `.tab-btn.active` underline (`inst:1222`). Same object, four different "I am chosen" pictures.
3. **List rows — six recipes, three divider techniques.** `.sidebar-item` 32h groove (`sb:123`) vs `.entity-row` 0.6rem + border-bottom (`inst:824`) vs `.theme-row` (`inst:1319`) vs `.backup-row` (`inst:1141`) vs `.arranger-item` (`inst:1465`) vs `.itemizer-item` (`inst:1598`) vs `.dropdown-item` (`inst:215` + `comp:229`). Border-bottom in five of them contradicts the "hairlines are inset box-shadow, never border" contract.
4. **Section rails — the same header in seven places, two of them fight.** `.sidebar-title` design skin (`des:43`) overrides the instrument skin (`inst:115`) but the instrument `::after` spacer is `transparent` (`inst:130-137`) while design paints a 1px `--mat-lo` rule (`des:56-62`), and the trailing `.action-icon` is 24px in design (`des:68`) vs 18px in instrument (`inst:139`). Meanwhile `.preset-menu-head` (`inst:182`), `.regex-group-header` (`inst:1814`), `.structured-group-header` (`inst:1893`), `.itemizer-bar` (`inst:1554`), `.edit-entity-field-head` (`inst:1094`) and `.modal-header` (`inst:742`) each re-derive it.
5. **Caret glyphs — four svg wrappers, one drawn mark, one text glyph.** `.chevron` (svg, `chat:295`) vs `.itemizer-chevron` (`inst:1662`) vs `.regex-chevron` (`inst:1838`) vs `.structured-chevron` (`inst:1917`) vs `.caret-mark` (`des:115`) vs `.arranger-handle` `⋮⋮` (`comp:377`) vs inline `style` + `icon_chevron_right(12)` in `partials/presets/prompt-block.html:23-34`. Only `.caret-mark` stays on the pixel grid — this is exactly the trap HANDOFF §8 records.
6. **Icon keys — seven recipes for a 20–28px square.** `.action-icon` filled `surface-3` (`comp:462`) vs `.action-btn` transparent (`inp:74`) vs `.btn-edit` hairline border (`inst:1262`) vs `.preset-item-action` bare (`inst:252`) vs `.sidebar-delete-btn` bare/raised (`inst:475` / `sb:230`) vs `.key-nav` bare (`lay:145`) vs `.toast-btn` bare (`anim:184`). The message toolbar (raised, `ms:241`) and the preset menu (bare, `inst:252`) are visible together.
7. **Fields — six skins.** `.form-control` (`comp:13`, `surface-2` + border + `--shadow-glow`) vs `#preset-selector .form-control` well (`des:90`) vs `.edit-block-ta` (`comp:79`, no fill, own border) vs `.arranger-input` borderless (`comp:437`) vs `.sampler-input` (`comp:707`) vs the base `:where(input,textarea,select)` (`lay:3`) — and `inst:916` re-transparents every field inside `.modal-content`.
8. **Destructive affordances — five treatments, one of them contradicts the contract.** `.btn-danger` bare + tint (`inst:495`) vs `.preset-item-action.danger` (`inst:272`, `--danger-tint`) vs shared `.action-icon.danger`/`.action-btn.text-danger` (`inst:1275`) vs raised `.sidebar-delete-btn` (`sb:230`) vs `.toast-error` red wash (`anim:152`) vs Tailwind `bg-danger` (`ui/media-utils.js:36`). HANDOFF §8: "no red washes" — `toast-error` is one.
9. **Empty states — five, two byte-identical.** `.regex-empty` (`inst:1883`) and `.structured-empty` (`inst:1973`) are the same block; plus `#chat-list [class*='border-dashed']` (`sb:108`), `.empty-text` (`comp:564`), `.edit-msg-drop-empty` (`inst:946`), and an inline `className = 'text-xs text-muted'` (`modals/providers.js:716`).
10. **Wells / recessed surfaces — six recipes.** `.status-panel` (`des:373`, inset + groove rows) vs `#staging-area > div` (`sb:393`, `ink-1`, no inset) vs `.media-thumb` (`comp:488`, border + radius) vs `.theme-swatch` (`inst:1359`) vs `.structured-preview` (`inst:1940`, no fill at all) vs `.regex-preview-out` (`inst:1865`, plain text). Two of them are on screen simultaneously (status panel + composer).
11. **Primary/create emphasis — four intensities for one verb.** solid accent `.send-btn` (`des:464`) vs accent tint `.btn-primary` (`inst:401`) vs flat green `.btn-create` (`inst:413`) vs raised+tinted `.btn-create` in the sidebar (`sb:58`) vs green ink only `.action-icon.is-create` (`inst:1763`).
12. **Pane collapse — two controls for one action.** `.left-tab`/`.right-tab` 40px full-height strips (`lay:264`, `lay:285`) vs the 24px `.sidebar-title > .action-icon` (`des:68`).

## §3 Two-owner / opt-out conflicts

| selector(s) that compete | where | who wins today | single-owner rule |
|---|---|---|---|
| `.left-sidebar .sidebar-title` | `inst:115` vs `des:43` | `des` (later, same specificity) | `.rail` owns header geometry; chassis owns its inset |
| `.left-sidebar .sidebar-section` | `lay:106` (layered) vs `inst:50` vs `des:28` | `des` | `surfaces/sidebar.css` |
| `.right-sidebar .sidebar-section` | `inst:65` vs `des:28` vs `sb:8` | `sb` | `surfaces/sidebar.css` |
| `.left-sidebar .status-panel` | `comp:321` vs `inst:356` vs `des:373` | `des` | `.well` |
| `.left-sidebar .tools-grid` | `comp:749` (unlayered) vs `inst:291` vs `des:332` | `des` | `surfaces/sidebar.css` |
| `.left-sidebar .tool-tile` | `comp:754` vs `inst:295` vs `des:338` | `des` | `.nav` |
| `.btn-secondary` | `comp:166` vs `inst:312` | `inst` (unlayered beats layer) | `.btn` |
| **`!` opt-out ladder:** `.btn-secondary:not(.tool-tile)` | `inst:314,322` | wins over any plain `.btn-secondary`, incl. a later one at equal specificity (0,2,0) | delete the ladder; `.tool-tile` becomes `.nav`, so nothing needs to opt out |
| **`!` opt-out ladder:** `.btn:not(.tool-tile):not(.btn-link)` | `inst:333,344` | 0,3,0 — **beats a plain `.btn` in `des`/`sb`** | delete; `.tool-tile`→`.nav`, `.btn-link`→`.link` |
| **`!` opt-out ladder:** `.btn-hero:not(.tool-tile):not(.btn-link)` | `inst:350` | 0,4,0 — same trap, wins over `.btn.lg` | delete |
| `.right-sidebar .sidebar-item` | `lay:172` vs `inst:432` vs `sb:123` | `sb` | `.row` |
| `.chat-pager-btn` / `.chat-pager-num` | `lay:228,247,253` vs `sb:294,311,317,323,336,341` | `sb` | `DECISION #7` |
| `.message` | `chat:71` vs `inst:532` vs `ms:13` | `ms` | `DECISION #11` |
| `.message-body` | `chat:166` vs `ms:294,469` | `ms` | `.well` |
| `.details > summary` | `chat:282` vs `inst:596` vs `ms:473` | `ms` inside `.message`, `inst` everywhere else | `.disclosure` |
| `.input-wrapper` / `#standard-input-container.input-wrapper` | `inp:121` vs `inst:677` vs `des:417` | `des` (id + class) | `.well` |
| `.attach-btn` | `inp:41` vs `inst:687` vs `des:449` | `des` | `.key.lg` |
| `.send-btn` | `inp:43` vs `inst:700` vs `des:464` | `des` | `.key.lg.primary` |
| `:where(input,textarea,select)` | `lay:3` (0 specificity) vs `comp:13` `.form-control` (0,1,0) vs `inst:911`/`inst:916` | `comp`/`inst` | `.field` only; no element-level defaults |
| `.right-sidebar [class*='border-dashed']` | `inst:469`, `sb:108` | `sb` | an attribute-substring selector is not an owner — `.empty` |
| `.hidden` | `tw:16` (`!important`) vs `inp:170` `.send-btn:not(.hidden)` animation | `tw` | `.hidden` stays a utility; `inp:170` must become a state class, not a `:not()` on a utility |
| **token ownership bug:** `--engrave`, `--ink-1`, `--ink-2`, `--hair-strong`, `--tint-2`, `--edge`, `--danger-ink`, `--success-tint*` are defined **only** in `inst:13-33`, but consumed by the new files — `des` 4×engrave, `sb` 1×engrave/3×ink-1/1×ink-2/2×tint-2/1×edge/3×success-tint, `ms` 5×ink-1/1×ink-2/3×hair-strong/1×edge/1×danger-ink | — | `inst` | deleting `instrument.css` silently un-styles the new skin; these tokens must move to `variables.css` in the same commit |
| `--radius-sm/md/lg` vs `--radius-control/panel` | `tokens.css:16-20` vs `variables.css` | both live, classes mix them (`sb` uses `--radius-control`, `inst` uses `--radius-sm`) | one scale: `--radius-control`/`--radius-panel` |

## §4 Needs a decision (12)

- **D1 checkbox** — `.checkbox` (`comp:36`), `.delete-mode-checkbox` (`chat:103`): a tick box is neither `.switch` (a latch) nor `.field`. Candidates: widen `.switch`, or add one `.check` shape. Trade-off: a new shape for one control vs a switch that lies about its semantics.
- **D2 badge / static marker** — `.arranger-badge`, `.badge-auto` (`comp:423,432`), `.key-badge` (`lay:158`), `.tree-dot` (`comp:727`): `.chip` implies toggleable, `.row-meta` implies readout. Trade-off: a non-interactive chip dilutes `chip`'s affordance; a readout with a fill dilutes `.row-meta`.
- **D3 slider** — `.styled-slider` (`comp:681`): `.field` with a `range` part, or its own primitive. Trade-off: it is an input (belongs to `.field`) whose only authored content is thumb geometry.
- **D4 radio switch** — `.radio-switch`, `.radio-inner` (`comp:259`; design already reskins it `des:243`): candidates `.switch`, or the D1 check shape. Trade-off: a round dot is the last circle in a language that removed circles everywhere else.
- **D5 helper text + hint tooltip + placeholders** (12 classes: `hint-wrapper`, `hint-icon`, `hint-danger/warning/success`, `arranger-note`, `itemizer-hint`, `empty-text`, `block-preview`, `modal-subhead`, `external-media-placeholder`, `external-media-label`, `edit-msg-drop-empty`): candidates `.empty` (inline caption) + a `.tooltip` overlay. Trade-off: fusing an overlay into an inline primitive hides a z-index/positioning contract.
- **D6 prose** — `.markdown-content` (35 rules, `chat:183-428` + `ms:316-412`), `.accent-quote` (`chat:431`): declare prose a *scope* owned by `surfaces/messages.css`, not a primitive. Trade-off: prose is not a control, so it may not belong in a control taxonomy at all.
- **D7 pager** — `.chat-pager`, `.chat-pager-btn` (`lay:222` vs `sb:285`): `.key`s in a strip, or a `.pager` composite. Trade-off: three controls that must share one 28h row; modelling it as `.key` alone re-derives the row every time.
- **D8 role edge** — `.bg-role-system` (`comp:514`) plus `.arranger-item.bg-role-*` (`inst:1480-1514`) and `.itemizer-role-*` (`inst:1615-1635`): `.row` + `role` modifier, or no role colour at all. Trade-off: role colour is semantic but three extra tints contradict "fill is never the state indicator".
- **D9 drag handle** — `.arranger-handle` (`comp:377`, a `⋮⋮` text glyph): `.key` (it is not clickable) or a drawn grip. Trade-off: it is the last text glyph in the chrome and reads off-grid, but a drawn grip is a new mark.
- **D10 loader** — `.message-spinner` (`chat:35`, offset-path trace) and `.gen-pulse` (`anim:62`): one `.spinner` primitive with two forms. Trade-off: two animations for one role is how the current pair drifted apart.
- **D11 raised frame** — `.message` (`ms:13`): `.card` is thumbnail+data, `.well` is recessed, `.modal` is the floating layer — nothing owns "raised panel". Trade-off: folding messages into `.card` gives `.card` two anatomies; a `.frame` primitive adds a 15th shape.
- **D12 non-field editable** — `.arranger-input` (`comp:437`, borderless), `.theme-color-input` (`inst:1435`): `.field` with `ghost`/`swatch` modifiers. Trade-off: both are inputs that must not read as form boxes, so the modifier set grows rather than the shape set.

## §5 Protected — do not rename

Re-derived by grepping `classList.`, `className =` and innerHTML templates in `static/js/**`.

| class | hook (cite) | styled by |
|---|---|---|
| `hidden` | `modal.js:69`, `providers.js:11` (39 sites) | `tw:16` utility |
| `active` | `providers.js:189`, `extensions.js:41`, `regex-scripts.js` (22 sites) | per primitive: `.row.active`, `.key.active`, `.chip.active`, `.switch.active`, `.tab.active` |
| `disabled` | `extensions.js:41`, `generation-ui.js:11` | per primitive (`:disabled` + `.disabled`) |
| `expanded` | `structured-responses.js:49`, `regex-scripts.js:73` | `.disclosure.expanded` |
| `details` | `edit-message.js:95` authors `details reasoning-block` | `.disclosure` |
| `drag-over` | `media-utils.js:82`, `edit-message.js` | `.well.drag-over` |
| `processed` | `message-renderer.js:166` | prose scope (`ms`) |
| `ready` | `message-renderer.js:171` | message list (`ms`) |
| `copied` | `message-renderer.js:154` | `.key.sm.copied` |
| `favorite-active` | `list-manager.js:76` | `.key.favorite-active` |
| `gen-pulse` | `generation-ui.js:53` (className) | `DECISION #10` |
| `message-placeholder` | `message-pruner.js:55` (className) | `layout-only: ms` |
| `media-thumb` | `media-utils.js:8` (className) | `.well` |
| `media-thumb-audio` | `media-utils.js:20` (innerHTML) — **missing from the brief's list** | `.well` inner |
| `media-thumb-close` | `media-utils.js:35` (className, Tailwind-positioned) | `.key.sm` |
| `toast`, `toast-text`, `toast-actions` | `notifications.js:111,118,125` (className) | `.toast` |
| `toast-btn` | `notifications.js:128,150` | `.key.sm` |
| `toast-leave` | `notifications.js:62` (classList) | `.toast` exit |
| `edit-block-ta` | `edit-message.js:62` (className) | `.field` |
| `textarea-wrapper` | `edit-message.js:71` (className) | `.field` wrapper |
| `reasoning-block` | `edit-message.js:95`, `generation-ui.js:34` | `.disclosure` |
| `regex-preview-error`, `structured-preview-error` | `regex-scripts.js:293`, `structured-responses.js:205` | `.well` + `.danger` |
| `text-danger` | markup only (`macros.html`), but it is the danger-ink hook | intent `.danger` |

Additional hooks the brief missed, same rule (keep the name, style via the primitive): `reasoning-open` (`generation-ui.js:34`, styled `ms:158`), `toast-info|toast-success|toast-error` (`notifications.js:111` prefix, styled `anim:146-160`), `toast-close` (`notifications.js:150`), `has-files` (`file-staging.js:70`), `is-selected` (`preset-selector.html:50`, `theme.html`), `slot-active` (`theme.html`), `message-ancestor` (`message.html:1`, styled `chat:76`), `sortable-ghost` (SortableJS; styled `inst:1517`), `htmx-swapping`/`htmx-settling` (`chat:143`), `rotate-90` (Alpine, `itemizer.html:35`). Also `hx-swap`/`hx-target` never carry class names — the only `hx-*` near a class is `partials/modals/providers.html:34` (`hx-swap="none" hx-on:htmx:after-request=...`), so no class is an htmx hook.

`active`, `disabled`, `expanded`, `details`, `hidden` are shared state names: they must resolve identically in every primitive (one block per state in the primitive layer, not per component).

## §6 Excluded

**Not mapped: 174 static class tokens in markup with no CSS rule at all** (verified: every token in `templates/`+`partials/` `class="..."` attributes with zero match in `static/css/**`). Do not map these — they are (a) Tailwind utilities (`flex`, `gap-*`, `text-xs`, `truncate`, `rotate-90`, `empty:hidden`, `group`, `z-50`, …), (b) Alpine expressions leaking into the attribute (`true`, `false`, `open`, `dropUp`, `darkId`, `lightId`, `selectedId`, `testingConfig`, `dirty`, `loading`), or (c) JS-only names with no styling intent:

`arranger-media-section` (`prompt-block.html:191`), `balance-loading` (`providers.html:27`), `block-media-btn`/`block-media-input`/`block-media-placeholder` (`edit-entity.html:73,81,85`), `char-block-media-section` (`edit-entity.html:68`), `continue-btn` (`message-toolbar.html:38`), `heavy` (`base.html:207`), `key-row-label` (`provider-create.html:47`), `media-thumb-img` (`macros.html:457`, authored `media-utils.js:31`), `message-toolbars` (`message-toolbars.html:3`), `msg-select-checkbox` (`message.html:9`), `normal-mode-actions` (`message-toolbar.html:1`), `reasoning-preview` (`prompt-block.html:94`), `regex-handle`/`regex-min`/`regex-max`/`regex-pattern`/`regex-replacement`/`regex-sample` (`regex-item.html:9,135,144,48,60,157`), `secret-select-btn` (`providers.html:116`), `structured-handle`/`structured-schema`/`structured-template`/`structured-sample` (`structured-item.html:9,50,64,76`), `theme-modal` (`theme.html:8`), `var-group-ids` (`var-group.html:5`), `hint-tooltip` (`base.html:299`, an id not a class).

**Out of scope by design:** ids, `data-ui`, `data-action`, `hx-*`, and `--thumb-size` style hooks.

## Count table (acceptance gate)

| §1 subsection | rows | cumulative |
|---|---|---|
| 1.1 `.btn` | 10 | 10 |
| 1.2 `.key` | 21 | 31 |
| 1.3 `.nav`/`.chip`/`.tab`/`.link` | 8 | 39 |
| 1.4 switch/intent/state | 24 | 63 |
| 1.5 `.field` | 12 | 75 |
| 1.6 `.row` + parts | 56 | 131 |
| 1.7 `.rail` | 9 | 140 |
| 1.8 `.well`/`.card`/media | 23 | 163 |
| 1.9 `.disclosure` + carets | 28 | 191 |
| 1.10 `.menu`/`.modal`/`.toast`/`.empty`/`.divider` | 17 | 208 |
| 1.11 message parts | 13 | 221 |
| 1.12 layout-only | 22 | **243** |

243 mapped exactly once · 153 primitive-mapped · 57 layout-only · 33 under 12 decisions · 25 protected.
