// Grid audit — the ruler.
//
// Measures the live app and fails when a box drifts off the 4px grid, when
// sibling rows disagree by a pixel, or when panes stop sharing a baseline.
// Run against a live server:  node tests/frontend/grid-audit.js http://127.0.0.1:8000
//
// Every surface added to the app must add its selectors here. A check that is
// not in this file is a check that does not exist.

const { chromium } = require('playwright');

const URL = process.argv[2] || process.env.FOCUS_URL || 'http://127.0.0.1:8000';
const U = 4;
const TOLERANCE = 0;

let failures = 0;
let checks = 0;

function fail(msg) {
  failures++;
  console.error('FAIL  ' + msg);
}

function ok(msg) {
  checks++;
  console.log('ok    ' + msg);
}

function offGrid(v) {
  return Math.abs(v / U - Math.round(v / U)) > 1e-6;
}

function checkGrid(name, r) {
  const bad = ['x', 'y', 'width', 'height'].filter((k) => offGrid(r[k]));
  checks++;
  if (!bad.length) return;
  failures++;
  const detail = bad.map((k) => `${k}=${r[k]}`).join(' ');
  console.error(`FAIL  ${name} off the ${U}px grid — ${detail}`);
}

function checkHeight(name, r, allowed) {
  checks++;
  if (allowed.includes(r.height)) return;
  failures++;
  console.error(`FAIL  ${name} height ${r.height} not in {${allowed.join(', ')}}`);
}

function checkSameRow(name, rects) {
  checks++;
  const tops = new Set(rects.map((r) => r.y));
  const heights = new Set(rects.map((r) => r.height));
  if (tops.size === 1 && heights.size === 1) return;
  failures++;
  console.error(`FAIL  ${name} rows disagree — tops {${[...tops]}} heights {${[...heights]}}`);
}

function checkSameColumn(name, rects) {
  checks++;
  const lefts = new Set(rects.map((r) => r.x));
  const widths = new Set(rects.map((r) => r.width));
  if (lefts.size === 1 && widths.size === 1) return;
  failures++;
  console.error(`FAIL  ${name} columns disagree — lefts {${[...lefts]}} widths {${[...widths]}}`);
}

function check(name, cond, detail) {
  checks++;
  if (cond) return;
  failures++;
  console.error(`FAIL  ${name}${detail ? ' — ' + detail : ''}`);
}

function checkInset(name, rect, pane, inset) {
  checks++;
  const dx = rect.x - pane.x;
  if (Math.abs(dx - inset) <= TOLERANCE) return;
  failures++;
  console.error(`FAIL  ${name} inset ${dx}px, expected ${inset}px`);
}

async function measure(page) {
  return page.evaluate(() => {
    const rect = (el) => {
      const b = el.getBoundingClientRect();
      return { x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height) };
    };
    const all = (sel) => [...document.querySelectorAll(sel)].filter((el) => el.getBoundingClientRect().height > 0).map(rect);
    const one = (sel) => {
      const el = document.querySelector(sel);
      return el ? rect(el) : null;
    };
    return {
      leftPane: one('.left-sidebar'),
      rightPane: one('.right-sidebar'),
      leftTitles: all('.left-sidebar .rail'),
      rightTitles: all('.right-sidebar .rail'),
      leftSections: all('.left-sidebar .sidebar-section'),
      preset: one('#preset-selector .preset-trigger'),
      newChat: one('.right-sidebar .rail-actions > .key'),
      tiles: all('.left-sidebar .nav'),
      status: one('.left-sidebar .well'),
      statusRows: all('.left-sidebar .well > .row'),
      varGroups: all('.left-sidebar .var-group'),
      varGroupHeaders: all('.left-sidebar .var-group > .row'),
      varLEDs: all('.left-sidebar .var-group > .row > .caret-mark'),
      varOptions: all('.left-sidebar .row.inset'),
      varKeys: all('.left-sidebar .row.inset > .check'),
      varAddRows: all('.left-sidebar .row.create'),
      composer: one('#standard-input-container'),
      chatInput: one('#chat-input'),
      attach: one('#standard-input-container .attach-btn'),
      send: one('#send-btn'),
      messageList: one('#message-list'),
      chatRows: all('.right-sidebar .row:not(.inset)'),
      chatLane: one('#chat-list [data-chat-list-scroll]'),
      chatLaneInner: (() => {
        const el = document.querySelector('#chat-list [data-chat-list-scroll]');
        return el ? Math.round(el.clientWidth) : null;
      })(),
      pagerButtons: all('.pager .key, .pager .pager-num'),
      messages: all('[data-ui="message"]'),
      rails: all('[data-ui="message"] .message-rail'),
      bodies: all('[data-ui="message"] [data-ui="message-body"]'),
    };
  });
}

// The modal chassis shares one inset across head, body and foot; the entity list
// inherits the row language. Measured with the tool modal open, because it is
// the widest surface and the one with a toolbar, a list and a footer at once.
async function measureModal(page) {
  return page.evaluate(() => {
    const rect = (el) => {
      const b = el.getBoundingClientRect();
      return { x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom) };
    };
    const ov = [...document.querySelectorAll('.modal-overlay')].reverse().find((e) => !e.classList.contains('hidden') && e.getBoundingClientRect().width);
    if (!ov) return null;
    const panel = ov.querySelector('.modal-panel');
    const head = panel.querySelector('.modal-head');
    const body = panel.querySelector('.modal-body');
    // A nested modal (retry, block edit) ships its own foot; only the one that
    // belongs to this panel counts.
    const foot = [...panel.querySelectorAll('.modal-foot')].find((f) => f.closest('.modal-panel') === panel);
    return {
      panel: rect(panel),
      head: rect(head),
      title: rect(panel.querySelector('.modal-title')),
      body: rect(body),
      bodyPad: getComputedStyle(body).paddingTop,
      firstKid: body.firstElementChild ? rect(body.firstElementChild) : null,
      entityRows: [...panel.querySelectorAll('.entity-row')].map(rect),
      entityAvatars: [...panel.querySelectorAll('.entity-row > .avatar')].map(rect),
      tabBar: panel.querySelector('.tab-bar') ? rect(panel.querySelector('.tab-bar')) : null,
      // A field and the control beside it must share one centre line: the
      // plates may differ in height, never in where they sit.
      fieldPairs: [...panel.querySelectorAll('.field-row, .field-inline, .field-range')].map((row) => {
        const f = row.querySelector('.field');
        const c = row.querySelector('.btn, .key, .chip');
        if (!f || !c) return null;
        return { field: rect(f), ctrl: rect(c) };
      }).filter(Boolean),
      foot: foot ? rect(foot) : null,
      footButtons: foot ? [...foot.querySelectorAll('.btn, .key')].map(rect) : [],
    };
  });
}

// The provider form is the app's densest settings column: three named groups,
// one caption column, one control line. Its failure mode is drift — a caption
// column that changes width per row, a control that stops sharing an edge with
// the field above it.
async function measureProviderForm(page) {
  return page.evaluate(() => {
    const rect = (el) => {
      const b = el.getBoundingClientRect();
      return { x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom) };
    };
    const panel = document.querySelector('#modal-provider-create > .modal-panel');
    if (!panel) return null;
    const rows = [...panel.querySelectorAll('#provider-form .row.setting')].filter((r) => r.getBoundingClientRect().height > 0);
    // The type plates are hidden until a type brings them; their rows are not
    // laid out and must not be measured.
    const labeled = [...panel.querySelectorAll('#provider-form .row.setting.labeled')].filter((r) => r.getBoundingClientRect().height > 0);
    return {
      panel: rect(panel),
      rails: [...panel.querySelectorAll('#provider-form .provider-section > .rail')].map(rect),
      rows: rows.map(rect),
      sections: [...new Set(rows.map((r) => r.closest('.provider-section')))].map(
        (section) => rows.filter((r) => r.closest('.provider-section') === section).map(rect),
      ),
      captions: labeled.map((r) => rect(r.querySelector('.row-title'))),
      fields: labeled
        .flatMap((r) => [...r.querySelectorAll(':scope > .field, :scope > .row-cell')])
        .map(rect),
      emptyNote: (() => {
        const el = panel.querySelector('#provider-form .provider-keys-empty > .row-meta');
        return el ? rect(el) : null;
      })(),
    };
  });
}

// The two text-editing modals: rails and fields on the modal inset, verbs on the
// foot inset. The message editor stacks one block per segment; the expander is
// one field and one foot.
async function measureTextModals(page) {
  return page.evaluate(() => {
    const rect = (el) => {
      const b = el.getBoundingClientRect();
      return { x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom) };
    };
    const read = (sel) => {
      const panel = document.querySelector(sel + ' > .modal-panel');
      if (!panel) return null;
      const q = (s) => panel.querySelector(s);
      const foot = [...panel.querySelectorAll('.modal-foot')].find((f) => f.closest('.modal-panel') === panel);
      return {
        panel: rect(panel),
        body: rect(q('.modal-body')),
        // A collapsed block hides its textarea; a hidden field has no edges.
        fields: [...panel.querySelectorAll('.msg-block-text, #text-expander-input')]
          .filter((f) => f.getBoundingClientRect().width > 0)
          .map(rect),
        rails: [...panel.querySelectorAll('.msg-block > .rail, .msg-attachments > .rail')].map(rect),
        railActions: [...panel.querySelectorAll('.rail-actions.flush > .key')].map(rect),
        foot: foot ? rect(foot) : null,
        footButtons: foot ? [...foot.querySelectorAll('.btn')].map(rect) : [],
        count: q('.msg-block [data-ui="block-count"]') ? rect(q('.msg-block [data-ui="block-count"]')) : null,
        // The attachment tray is one gallery grid whose thumb layer dissolves
        // into it (display: contents) and hugs its rows.
        mediaTray: (() => {
          const tray = q('#edit-msg-media');
          if (!tray) return null;
          const kid = tray.querySelector('#edit-msg-attachments > *');
          const note = q('#edit-msg-att-empty');
          const layer = q('#edit-msg-attachments');
          return {
            tray: rect(tray),
            note: note && note.getBoundingClientRect().width > 0 ? rect(note) : null,
            first: kid ? rect(kid) : null,
            layer: layer ? getComputedStyle(layer).display : null,
          };
        })(),
      };
    };
    return { editMessage: read('#modal-edit-message'), expander: read('#modal-text-expander') };
  });
}

// The entity editor: two panes, each naming its groups with a rail. The pane
// gutter, the rail insets and the identity rows are the geometry that regresses
// when this modal is touched.
async function measureEntityEditor(page) {
  return page.evaluate(() => {
    const rect = (el) => {
      const b = el.getBoundingClientRect();
      return { x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom) };
    };
    const panel = document.querySelector('#modal-edit-character > .modal-panel');
    if (!panel) return null;
    const q = (sel) => panel.querySelector(sel);
    const rows = [...panel.querySelectorAll('.edit-fields > .row')].filter((r) => r.getBoundingClientRect().height > 0);
    return {
      panel: rect(panel),
      side: rect(q('.edit-entity-side')),
      main: rect(q('.edit-entity-main')),
      identityRail: rect(q('.edit-entity-side > .rail')),
      descRail: rect(q('.edit-doc > .rail')),
      greetRail: rect(q('.edit-greeting > .rail')),
      desc: rect(q('.edit-doc > .edit-text')),
      greet: rect(q('.edit-greeting > .edit-text')),
      avatar: rect(q('.edit-avatar')),
      media: rect(q('#edit-char-media-section')),
      captions: rows.map((r) => rect(r.querySelector('.row-title'))),
      fields: rows.flatMap((r) => [...r.querySelectorAll(':scope > .field, :scope > .row-cell')]).map(rect),
      door: rect(q('[data-action="actionOpenCharBlocks"]')),
      legacy: rect(q('#edit-char-card-fields')),
      greetKeys: [...panel.querySelectorAll('.edit-greeting .rail-actions > .key')].map(rect),
      footBtn: rect(q('.modal-foot .btn.primary')),
    };
  });
}

// The saved-key library: one column of readout rows whose verbs keep the row's
// own content edge. The add form is a separate modal, so the list must not
// change height when it opens.
async function measureSecrets(page) {
  return page.evaluate(() => {
    const rect = (el) => {
      const b = el.getBoundingClientRect();
      return { x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom) };
    };
    const panel = document.querySelector('#modal-secrets > .modal-panel');
    if (!panel) return null;
    const rows = [...panel.querySelectorAll('.secret-row')];
    return {
      panel: rect(panel),
      lane: rect(panel.querySelector('.modal-band-lane')),
      rows: rows.map(rect),
      titles: rows.map((r) => rect(r.querySelector('.row-title'))),
      verbs: rows.map((r) => rect(r.querySelector('.row-actions > .key:last-child'))),
    };
  });
}

// The presets collection: one column of two-line rows. The identity stack and
// the verb cluster must both keep the lane's inset per row, or the list stops
// reading as one column.
async function measurePresetRows(page) {
  return page.evaluate(() => {
    const rect = (el) => {
      const b = el.getBoundingClientRect();
      return { x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom) };
    };
    const panel = document.querySelector('#modal-presets > .modal-panel');
    if (!panel) return null;
    const rows = [...panel.querySelectorAll('.preset-row')];
    if (!rows.length) return null;
    return {
      panel: rect(panel),
      lane: rect(panel.querySelector('.modal-band-lane')),
      rows: rows.map(rect),
      titles: rows.map((r) => rect(r.querySelector('.row-title'))),
      metas: rows.map((r) => rect(r.querySelector('.row-meta'))),
      verbs: rows.map((r) => rect(r.querySelector('.row-actions > .key:last-child'))),
    };
  });
}

// The banded modal chassis: a rail, an optional toolbar, the list lane, an
// optional foot. The vertical rhythm is the thing that keeps regressing — a
// rail flush against the lane edge reads as "no margin at the top".
async function measureBands(page) {
  return page.evaluate(() => {
    const rect = (el) => {
      const b = el.getBoundingClientRect();
      return { x: b.x, y: b.y, width: b.width, height: b.height, right: b.right, bottom: b.bottom };
    };
    const ov = [...document.querySelectorAll('.modal-overlay')].reverse().find((e) => !e.classList.contains('hidden') && e.getBoundingClientRect().width);
    if (!ov) return null;
    const panel = ov.querySelector('.modal-panel');
    const head = panel.querySelector('.modal-head');
    const body = panel.querySelector('.modal-body');
    const container = body.querySelector('.modal-bands');
    const bands = container ? [...container.children] : [];
    const rail = body.querySelector('.modal-band-head .rail');
    const lane = body.querySelector('.modal-band-lane');
    const foot = body.querySelector('.modal-band-foot');
    const headBand = body.querySelector('.modal-band-head');
    // A hidden band is not a band: the tool tabs hide their search row while
    // tools are off, and a `display:none` sibling measures 0×0.
    const laidOut = (el) => el && el.getBoundingClientRect().height > 0;
    const nextOf = (el) => {
      let n = el ? el.nextElementSibling : null;
      while (n && !laidOut(n)) n = n.nextElementSibling;
      return n;
    };
    const next = nextOf(headBand);
    const firstKid = lane ? [...lane.children].find(laidOut) : null;
    const row = lane && lane.querySelector('[data-ui="entity-row"], [data-ui="arranger-item"], [data-ui="char-block"], .itemizer-item, .row');
    const last = bands[bands.length - 1];
    // A foot may carry a hidden popover (the arranger's add-block menu); only
    // laid-out verbs count.
    const footButtons = foot
      ? [...foot.querySelectorAll('.btn, .key')].filter((e) => e.getBoundingClientRect().width > 0)
      : [];
    const modalFoot = panel.querySelector(':scope > .modal-foot');
    const split = body.querySelector('.theme-split');
    const cols = split ? [...split.children] : [];
    return {
      panel: rect(panel),
      head: rect(head),
      body: rect(body),
      rail: rail ? rect(rail) : null,
      lane: lane ? rect(lane) : null,
      row: row ? rect(row) : null,
      next: next ? rect(next) : null,
      firstKid: firstKid ? rect(firstKid) : null,
      tabs: panel.querySelector('.tab-bar') ? rect(panel.querySelector('.tab-bar')) : null,
      foot: foot ? rect(foot) : null,
      last: last ? rect(last) : null,
      footButtons: footButtons.map(rect),
      modalFoot: modalFoot ? rect(modalFoot) : null,
      modalFootButtons: modalFoot ? [...modalFoot.querySelectorAll('.btn, .key')].map(rect) : [],
      columns: cols.map(rect),
      bandCount: bands.length,
    };
  });
}

// Half-pixel heights are the tell of an inline-level control sitting in a line
// box: the wrapper grows past the control by the font's own half-leading, and
// every band below it inherits the .5. The primitives are integer-sized, so a
// fractional box in a modal is always a wrapper that should be a flex box.
async function measureOffbeat(page) {
  return page.evaluate(() => {
    const ov = [...document.querySelectorAll('.modal-overlay')].reverse().find((e) => !e.classList.contains('hidden') && e.getBoundingClientRect().width);
    if (!ov) return [];
    const out = [];
    const sel = '.modal-head, .modal-body, .modal-foot, .modal-band-head, .modal-band-toolbar, .modal-band-lane, .modal-band-foot, .card, .row, .well, .field, .check, .switch, .tag, .rail';
    for (const el of ov.querySelectorAll(sel)) {
      // A textarea is sized from its content's scrollHeight, which is a font
      // measurement, not a box on the grid.
      if (el.tagName === 'TEXTAREA') continue;
      const b = el.getBoundingClientRect();
      if (b.width < 2 || b.height < 2) continue;
      if (Math.abs(b.height - Math.round(b.height)) > 0.05) {
        out.push({ el: el.tagName + '.' + String(el.className).split(' ').slice(0, 3).join('.'), height: +b.height.toFixed(2) });
      }
    }
    return out;
  });
}

(async () => {
  const browser = await chromium.launch({ channel: 'chrome' });
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  await page.goto(URL + '/chat', { waitUntil: 'networkidle' });
  // The option rows only exist while a variable group is expanded; the audit's
  // own context starts collapsed.
  const firstGroup = page.locator('.left-sidebar .var-group > .row .row-title').first();
  if (await firstGroup.count()) {
    await firstGroup.click();
    await page.waitForTimeout(300);
  }
  const m = await measure(page);
  const offbeat = [];
  const sweep = async (state) => {
    for (const o of await measureOffbeat(page)) offbeat.push({ state, ...o });
  };
  await page.locator('.left-sidebar .nav', { hasText: 'Characters' }).first().click();
  await page.waitForTimeout(800);
  await sweep('characters');
  const mmEntity = await measureModal(page);
  const mmEntityBands = await measureBands(page);
  await page.locator('#char-modal-grid .entity-row [aria-label="Edit character"]').first().click();
  await page.waitForTimeout(900);
  await sweep('character editor');
  const mmEditor = await measureEntityEditor(page);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.locator('[data-ui="message"]').nth(1).hover();
  await page.waitForTimeout(300);
  await page.locator('[data-ui="message"]').nth(1).locator('[data-action="actionEditMessage"]').click();
  await page.waitForTimeout(1100);
  await sweep('message editor');
  const mmEditMessage = await measureTextModals(page);
  await page.locator('#modal-edit-message .msg-block .rail-actions .key').first().click();
  await page.waitForTimeout(700);
  await sweep('text expander');
  const mmExpander = await measureTextModals(page);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(400);
  await page.locator('.left-sidebar .nav', { hasText: 'Personas' }).first().click();
  await page.waitForTimeout(800);
  await sweep('personas');
  const mmPersonaBands = await measureBands(page);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.locator('#preset-selector .preset-trigger').click();
  await page.waitForTimeout(900);
  await sweep('presets');
  const mmPresets = await measureBands(page);
  const mmPresetRows = await measurePresetRows(page);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.locator('.left-sidebar .nav', { hasText: 'Providers' }).first().click();
  await page.waitForTimeout(800);
  await sweep('providers');
  const mmProviders = await measureBands(page);
  await page.locator('button[onclick="openSecretsManager()"]').click();
  await page.waitForTimeout(800);
  await sweep('saved keys');
  const mmSecrets = await measureSecrets(page);
  const mmSecretsBands = await measureBands(page);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.locator('[data-action="actionOpenProviderCreateModal"]').click();
  await page.waitForTimeout(800);
  await sweep('provider form');
  const mmFoot = await measureModal(page);
  const mmProviderForm = await measureProviderForm(page);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.locator('.left-sidebar .nav', { hasText: 'Itemizer' }).first().click();
  await page.waitForTimeout(900);
  await sweep('itemizer');
  const mmItemizer = await measureBands(page);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.locator('.left-sidebar .nav', { hasText: 'Arranger' }).first().click();
  await page.waitForTimeout(900);
  await sweep('arranger');
  const mmArranger = await measureBands(page);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.locator('.left-sidebar .nav', { hasText: 'Samplers' }).first().click();
  await page.waitForTimeout(900);
  await sweep('sampler');
  const mmSampler = await measureBands(page);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.locator('.left-sidebar .nav', { hasText: 'Advanced' }).first().click();
  await page.waitForTimeout(1200);
  await sweep('advanced');
  const mmAdvanced = await measureBands(page);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await page.locator('.left-sidebar .nav', { hasText: 'Themes' }).first().click();
  await page.waitForTimeout(900);
  await sweep('themes');
  const mmTheme = await measureBands(page);
  await browser.close();

  const inset = 12;

  checkGrid('left pane', m.leftPane);
  checkGrid('right pane', m.rightPane);
  [...m.leftTitles, ...m.rightTitles].forEach((r, i) => checkGrid('rail ' + i, r));
  [...m.leftSections].forEach((r, i) => checkGrid('left section ' + i, r));
  checkGrid('preset selector', m.preset);
  if (m.newChat) checkGrid('new chat key', m.newChat);
  m.tiles.forEach((r, i) => checkGrid('tool tile ' + i, r));
  checkGrid('status panel', m.status);
  m.statusRows.forEach((r, i) => checkGrid('status row ' + i, r));
  m.varGroups.forEach((r, i) => checkGrid('var group ' + i, r));
  m.varGroupHeaders.forEach((r, i) => checkGrid('var group header ' + i, r));
  m.varOptions.forEach((r, i) => checkGrid('var option ' + i, r));
  m.varKeys.forEach((r, i) => checkGrid('var key ' + i, r));
  m.varAddRows.forEach((r, i) => checkGrid('var add row ' + i, r));
  checkGrid('composer', m.composer);
  checkGrid('chat input', m.chatInput);
  checkGrid('send', m.send);

  if (m.leftTitles.length) checkInset('left rail', m.leftTitles[0], m.leftPane, inset);
  if (m.rightTitles.length) checkInset('right rail', m.rightTitles[0], m.rightPane, inset);
  if (m.preset) checkInset('preset selector', m.preset, m.leftPane, inset);

  if (m.leftTitles.length && m.rightTitles.length) {
    checkSameRow('pane rails', [m.leftTitles[0], m.rightTitles[0]]);
  }
  checkHeight('preset selector', m.preset, [28, 32]);
  checkHeight('new chat key', m.newChat, [24, 28, 32]);
  m.tiles.forEach((r, i) => checkHeight('tool tile ' + i, r, [28, 32]));
  m.statusRows.forEach((r, i) => checkHeight('status row ' + i, r, [20, 24, 28]));
  m.varGroupHeaders.forEach((r, i) => checkHeight('var group header ' + i, r, [28, 32]));
  m.varOptions.forEach((r, i) => checkHeight('var option ' + i, r, [24, 28]));
  m.varKeys.forEach((r, i) => checkHeight('var key ' + i, r, [16]));
  m.varAddRows.forEach((r, i) => checkHeight('var add row ' + i, r, [28, 32]));
  // The active chat's preset may legitimately have no variables (or every group
  // may be collapsed); those checks only run when the surface is on screen.
  if (m.varGroups.length) {
    checkInset('var group', m.varGroups[0], m.leftPane, inset);
  }
  if (m.varGroupHeaders.length) {
    check(
      'var labels share one left edge',
      m.varGroupHeaders.every((r) => r.x === m.varGroupHeaders[0].x),
    );
  }
  if (m.varOptions.length && m.varGroups.length) {
    check(
      'var options indent past their group name',
      m.varOptions.every((r) => r.x >= m.varGroups[0].x),
    );
  }
  checkHeight('composer', m.composer, [40, 48, 56]);
  checkHeight('chat input', m.chatInput, [28, 32, 36]);
  checkHeight('send', m.send, [28, 32]);

  const firstRow = m.tiles.slice(0, 2);
  check(
    'tile columns tile at an 8px gutter',
    firstRow.length === 2 &&
      firstRow[0].width === firstRow[1].width &&
      firstRow[1].x === firstRow[0].x + firstRow[0].width + 8,
  );
  m.tiles.forEach((r, i) => {
    if (i < 2) return;
    const prev = m.tiles[i - 2];
    check(
      `tile ${i} sits one row below tile ${i - 2} at an 8px gutter`,
      r.y === prev.y + prev.height + 8 && r.x === prev.x,
    );
  });

  m.chatRows.forEach((r, i) => checkGrid('chat row ' + i, r));
  if (m.chatRows.length) {
    // Rows live inside the scroll lane, so the lane owns the inset and the rows
    // span its content box — the bar lane is subtracted, which is why this is
    // measured against the lane and not the pane.
    check('chat scroll lane sits on the pane inset', m.chatLane.x - m.rightPane.x === inset);
    check(
      'chat rows fill the scroll lane',
      m.chatRows.every((r) => r.x === m.chatLane.x && r.width === m.chatLaneInner),
      `row x=${m.chatRows[0].x} w=${m.chatRows[0].width} lane x=${m.chatLane.x} inner=${m.chatLaneInner}`,
    );
    const heights = new Set(m.chatRows.map((r) => r.height));
    check('chat rows share one height of 32', heights.size === 1 && [...heights][0] === 32, `heights {${[...heights]}}`);
    const pitches = new Set(m.chatRows.slice(1).map((r, i) => r.y - m.chatRows[i].y));
    check('chat rows sit on a constant pitch', pitches.size <= 1, `pitches {${[...pitches]}}`);
  }
  m.pagerButtons.forEach((r, i) => checkGrid('pager button ' + i, r));

  m.messages.forEach((r, i) =>
    check(
      `message ${i} sits on the content column`,
      r.x % 4 === 0 && r.width % 4 === 0 && r.width === m.messageList.width,
      `x=${r.x} w=${r.width} column=${m.messageList.width}`,
    ),
  );
  m.rails.forEach((r, i) => check(`message ${i} rail is 32`, r.height === 32, `h=${r.height}`));
  m.bodies.forEach((r, i) => {
    const frame = m.messages[i];
    const dx = r.x - frame.x;
    check(
      `message ${i} screen is inset 8 with width frame-16`,
      dx === 8 && r.width === frame.width - 16 && r.x % 4 === 0,
      `inset=${dx} w=${r.width} frame=${frame.width}`,
    );
  });

  check(
    'composer sits on the message column',
    m.composer.x === m.messageList.x && m.composer.width === m.messageList.width,
    `composer x=${m.composer.x} w=${m.composer.width} column x=${m.messageList.x} w=${m.messageList.width}`,
  );

  // ── Modal chassis: one inset across head, body and panel edges ──
  const modalPad = 24;
  if (mmEntity) {
    const p = mmEntity.panel;
    checkGrid('modal panel', p);
    checkHeight('modal head', mmEntity.head, [64]);
    check(
      'modal title is inset equally above and below',
      mmEntity.title.y - p.y === modalPad && mmEntity.head.bottom - (mmEntity.title.y + mmEntity.title.height) === modalPad,
      `above=${mmEntity.title.y - p.y} below=${mmEntity.head.bottom - (mmEntity.title.y + mmEntity.title.height)}`,
    );
    check(
      'modal title sits on the panel inset (top and left)',
      mmEntity.title.x - p.x === modalPad && mmEntity.title.y - p.y === modalPad,
      `dx=${mmEntity.title.x - p.x} dy=${mmEntity.title.y - p.y}`,
    );
    check(
      'modal bands bleed to the panel edges',
      mmEntityBands &&
        mmEntityBands.lane &&
        mmEntityBands.lane.x === p.x &&
        mmEntityBands.lane.right === p.right,
      mmEntityBands && mmEntityBands.lane
        ? `left=${mmEntityBands.lane.x - p.x} right=${p.right - mmEntityBands.lane.right}`
        : 'no lane measured',
    );
    const rows = mmEntity.entityRows;
    if (rows.length) {
      const heights = new Set(rows.map((r) => r.height));
      check('entity rows share one height of 32', heights.size === 1 && [...heights][0] === 32, `heights {${[...heights]}}`);
      // Rows flow column-major, so a column is compared with itself.
      const columns = [...new Set(rows.map((r) => r.x))];
      columns.forEach((x) => {
        const col = rows.filter((r) => r.x === x);
        const pitches = new Set(col.slice(1).map((r, i) => r.y - col[i].y));
        check('entity rows sit on a constant pitch at x=' + x, pitches.size <= 1, `pitches {${[...pitches]}}`);
      });
      check('entity list uses two columns', columns.length === 2, `columns {${columns}}`);
      check('entity columns are equal width', new Set(rows.map((r) => r.width)).size === 1);
    }
    mmEntity.entityAvatars.forEach((r, i) => {
      check(`entity avatar ${i} is a 24px square`, r.width === 24 && r.height === 24, `${r.width}x${r.height}`);
    });
    if (rows.length && mmEntity.entityAvatars.length) {
      check('entity avatar rides the row centre', mmEntity.entityAvatars[0].y - rows[0].y === 4, `dy=${mmEntity.entityAvatars[0].y - rows[0].y}`);
    }
  }
  // ── Provider form: the settings column's caption line and control line ──
  if (mmProviderForm) {
    const p = mmProviderForm.panel;
    const rails = mmProviderForm.rails;
    check('provider form: three named groups', rails.length === 3, `rails ${rails.length}`);
    rails.forEach((r, i) =>
      check(
        `provider form: group rail ${i} sits on the modal inset`,
        r.x === p.x + modalPad && p.right - r.right === modalPad,
        `left=${r.x - p.x} right=${p.right - r.right}`,
      ),
    );
    const rows = mmProviderForm.rows;
    check(
      'provider form: every settings line spans the column',
      new Set(rows.map((r) => r.x)).size === 1 && new Set(rows.map((r) => r.right)).size === 1,
      `x {${[...new Set(rows.map((r) => r.x))]}} right {${[...new Set(rows.map((r) => r.right))]}}`,
    );
    mmProviderForm.sections.forEach((section, i) => {
      const pitches = new Set(section.slice(1).map((r, j) => r.y - section[j].y));
      check(`provider form: group ${i} sits on one pitch`, pitches.size <= 1, `pitches {${[...pitches]}}`);
    });
    const caps = mmProviderForm.captions;
    check(
      'provider form: captions share one column',
      new Set(caps.map((c) => c.x)).size === 1 && new Set(caps.map((c) => c.width)).size === 1,
      `x {${[...new Set(caps.map((c) => c.x))]}} w {${[...new Set(caps.map((c) => c.width))]}}`,
    );
    const fields = mmProviderForm.fields;
    check(
      'provider form: controls start on the caption column',
      new Set(fields.map((f) => f.x)).size === 1,
      `x {${[...new Set(fields.map((f) => f.x))]}}`,
    );
    // The row's own 8px inset is the content edge; the model field stops short
    // of it because the fetch key takes the corner.
    const contentEdge = rows[0].right - 8;
    check(
      'provider form: controls close on the row content edge',
      fields.every((f) => f.right <= contentEdge) && fields.some((f) => f.right === contentEdge),
      `rights {${[...new Set(fields.map((f) => f.right))]}} edge=${contentEdge}`,
    );
    if (mmProviderForm.emptyNote) {
      check(
        'provider form: the empty key list keeps the caption line',
        mmProviderForm.emptyNote.x === caps[0].x,
        `note=${mmProviderForm.emptyNote.x} caption=${caps[0].x}`,
      );
    }
  }

  // ── Presets: one column of two-line rows ──
  if (mmPresetRows) {
    const p = mmPresetRows.panel;
    const rows = mmPresetRows.rows;
    checkHeight('preset row', rows[0], [48]);
    const pitches = new Set(rows.slice(1).map((r, i) => r.y - rows[i].y));
    check('preset rows sit on a constant pitch', pitches.size <= 1, `pitches {${[...pitches]}}`);
    check(
      'preset rows span the lane',
      new Set(rows.map((r) => r.x)).size === 1 && new Set(rows.map((r) => r.right)).size === 1,
      `x {${[...new Set(rows.map((r) => r.x))]}} right {${[...new Set(rows.map((r) => r.right))]}}`,
    );
    check(
      'preset titles share one column',
      new Set(mmPresetRows.titles.map((t) => t.x)).size === 1,
      `x {${[...new Set(mmPresetRows.titles.map((t) => t.x))]}}`,
    );
    check(
      'preset meta sits under its title',
      new Set(mmPresetRows.metas.map((m) => m.x)).size === 1 &&
        mmPresetRows.metas[0].x === mmPresetRows.titles[0].x,
      `meta=${mmPresetRows.metas[0].x} title=${mmPresetRows.titles[0].x}`,
    );
    check(
      'preset verbs share one right edge',
      new Set(mmPresetRows.verbs.map((v) => v.right)).size === 1,
      `rights {${[...new Set(mmPresetRows.verbs.map((v) => v.right))]}}`,
    );
    check(
      'preset rows close on the panel inset',
      Math.abs(p.right - rows[0].right - modalPad) < 1,
      `right=${(p.right - rows[0].right).toFixed(1)}`,
    );
  }

  // ── Entity editor: two panes, rails on the pane insets ──
  if (mmEditor) {
    const p = mmEditor.panel;
    const gutter = 24;
    check('editor identity pane is 336 wide', mmEditor.side.width === 336, `w=${mmEditor.side.width}`);
    check(
      'editor panes keep one gutter',
      mmEditor.main.x - mmEditor.side.right === gutter,
      `gutter=${mmEditor.main.x - mmEditor.side.right}`,
    );
    check(
      'editor content pane closes on the modal inset',
      Math.abs(p.right - mmEditor.main.right - modalPad) < 1,
      `right=${(p.right - mmEditor.main.right).toFixed(1)}`,
    );
    check(
      'editor identity rail sits on its pane edge',
      mmEditor.identityRail.x === mmEditor.side.x && Math.abs(mmEditor.identityRail.right - mmEditor.side.right) < 12,
      `rail=${mmEditor.identityRail.x}..${mmEditor.identityRail.right} pane=${mmEditor.side.x}..${mmEditor.side.right}`,
    );
    [mmEditor.descRail, mmEditor.greetRail].forEach((r, i) =>
      check(
        `editor content rail ${i} spans the content pane`,
        r.x === mmEditor.main.x && Math.abs(r.right - mmEditor.main.right) < 1,
        `rail=${r.x}..${r.right} pane=${mmEditor.main.x}..${mmEditor.main.right}`,
      ),
    );
    [['description', mmEditor.desc, mmEditor.descRail], ['greeting', mmEditor.greet, mmEditor.greetRail]].forEach(([name, field, rail]) =>
      check(
        `editor ${name} field spans its rail`,
        field.x === rail.x && Math.abs(field.right - rail.right) < 1,
        `field=${field.x}..${field.right} rail=${rail.x}..${rail.right}`,
      ),
    );
    check('editor portrait is a 96px square', mmEditor.avatar.width === 96 && mmEditor.avatar.height === 96, `${mmEditor.avatar.width}x${mmEditor.avatar.height}`);
    check(
      'editor media tray shares both edges with the identity controls',
      mmEditor.media.x === mmEditor.fields[0].x &&
        Math.abs(mmEditor.media.right - mmEditor.fields[0].right) < 1,
      `tray=${mmEditor.media.x}..${mmEditor.media.right} control=${mmEditor.fields[0].x}..${mmEditor.fields[0].right}`,
    );
    check(
      'editor portrait sits on the identity control column',
      mmEditor.avatar.x === mmEditor.fields[0].x,
      `avatar=${mmEditor.avatar.x} control=${mmEditor.fields[0].x}`,
    );
    check(
      'editor media tray is the fixed three-row gallery',
      mmEditor.media.height === 176,
      `h=${mmEditor.media.height}`,
    );
    const caps = mmEditor.captions;
    check(
      'editor identity captions share one column',
      new Set(caps.map((c) => c.x)).size === 1 && new Set(caps.map((c) => c.width)).size === 1,
      `x {${[...new Set(caps.map((c) => c.x))]}} w {${[...new Set(caps.map((c) => c.width))]}}`,
    );
    const fields = mmEditor.fields;
    check(
      'editor identity controls share both edges',
      new Set(fields.map((f) => f.x)).size === 1 && new Set(fields.map((f) => f.right)).size === 1,
      `x {${[...new Set(fields.map((f) => f.x))]}} right {${[...new Set(fields.map((f) => f.right))]}}`,
    );
    // The extras are rows of the column, not controls of a caption row: they
    // share the pane's content edges with each other.
    check(
      'editor extras share the column edges',
      mmEditor.legacy.x === mmEditor.door.x && mmEditor.legacy.right === mmEditor.door.right &&
        mmEditor.door.x === mmEditor.side.x,
      `door=${mmEditor.door.x}..${mmEditor.door.right} legacy=${mmEditor.legacy.x}..${mmEditor.legacy.right} pane=${mmEditor.side.x}`,
    );
    const lastKey = mmEditor.greetKeys[mmEditor.greetKeys.length - 1];
    check(
      'editor greeting verbs close on the rail right edge',
      lastKey && Math.abs(lastKey.right - mmEditor.greetRail.right) < 1,
      `last=${lastKey && lastKey.right} rail=${mmEditor.greetRail.right}`,
    );
    check(
      'editor foot verb closes on the panel inset',
      Math.abs(p.right - mmEditor.footBtn.right - modalPad) < 1 &&
        Math.abs(p.bottom - mmEditor.footBtn.bottom - 16) < 1,
      `right=${(p.right - mmEditor.footBtn.right).toFixed(1)} bottom=${(p.bottom - mmEditor.footBtn.bottom).toFixed(1)}`,
    );
  }

  // ── Text modals: rails, fields and foot verbs on the modal inset ──
  [
    ['message editor', mmEditMessage && mmEditMessage.editMessage],
    ['text expander', mmExpander && mmExpander.expander],
  ].forEach(([name, m]) => {
    if (!m) {
      check(name + ': measured', false, 'modal not open');
      return;
    }
    const p = m.panel;
    m.fields.forEach((f, i) =>
      check(
        `${name}: field ${i} spans the body`,
        Math.abs(f.x - (p.x + modalPad)) < 1 && Math.abs(p.right - modalPad - f.right) < 1,
        `field=${f.x}..${f.right} body=${p.x + modalPad}..${p.right - modalPad}`,
      ),
    );
    m.rails.forEach((r, i) =>
      check(
        `${name}: rail ${i} sits on the modal inset`,
        Math.abs(r.x - (p.x + modalPad)) < 1 && Math.abs(p.right - modalPad - r.right) < 1,
        `rail=${r.x}..${r.right} inset=${p.x + modalPad}..${p.right - modalPad}`,
      ),
    );
    m.railActions.forEach((a, i) =>
      check(
        `${name}: rail verb ${i} closes on the modal inset`,
        Math.abs(p.right - modalPad - a.right) < 1,
        `right=${(p.right - modalPad - a.right).toFixed(1)}`,
      ),
    );
    if (m.mediaTray) {
      const t = m.mediaTray;
      check('message editor: attachment tray hugs one row when empty', t.first || t.tray.height === 72, `h=${t.tray.height}`);
      check('message editor: attachment tray holds the gallery height', t.tray.height <= 176, `h=${t.tray.height}`);
      check('message editor: thumbs are grid items of the tray', t.layer === 'contents', t.layer);
      check(
        'message editor: thumbs sit on the tray inset',
        !t.first || (t.first.x - t.tray.x === 8 && t.first.width === 48),
        t.first ? `x=${t.first.x - t.tray.x} w=${t.first.width}` : 'no thumbs',
      );
      check(
        'message editor: the empty note spans the tray',
        !t.note || (t.note.x - t.tray.x === 8 && t.note.width > 48),
        t.note ? `x=${t.note.x - t.tray.x} w=${t.note.width}` : 'no note',
      );
    }
    const lastBtn = m.footButtons[m.footButtons.length - 1];
    check(
      `${name}: foot closes on the panel inset`,
      lastBtn && Math.abs(p.right - lastBtn.right - modalPad) < 1 && Math.abs(p.bottom - lastBtn.bottom - 16) < 1,
      lastBtn ? `right=${(p.right - lastBtn.right).toFixed(1)} bottom=${(p.bottom - lastBtn.bottom).toFixed(1)}` : 'no foot verbs',
    );
  });

  // ── Banded modal chassis: one vertical rhythm across every list modal ──
  // One number separates a band's content from anything above or below it.
  const bandPad = 16;
  [
    ['characters', mmEntityBands],
    ['personas', mmPersonaBands],
    ['providers', mmProviders],
    ['secrets', mmSecretsBands],
    ['presets', mmPresets],
    ['itemizer', mmItemizer],
    ['arranger', mmArranger],
    ['samplers', mmSampler],
    ['advanced', mmAdvanced],
    ['themes', mmTheme],
  ].forEach(([name, b]) => {
    if (!b) return;
    const p = b.panel;
    if (!b.rail) {
      check(name + ': banded modal has a rail', false, 'no .rail in .modal-band-head');
      return;
    }
    check(
      name + ': rail sits on the modal inset',
      Math.abs(b.rail.x - p.x - modalPad) < 1 && Math.abs(p.right - b.rail.right - modalPad) < 1,
      `left=${(b.rail.x - p.x).toFixed(1)} right=${(p.right - b.rail.right).toFixed(1)}`,
    );
    // One rhythm for the whole chassis: the rail has the modal inset above it
    // (from the head groove or the tab strip) and the same below it.
    const above = b.tabs || b.head;
    check(
      name + ': rail sits one band pad under the band above it',
      Math.abs(b.rail.y - above.bottom - bandPad) < 1,
      `gap=${(b.rail.y - above.bottom).toFixed(1)}`,
    );
    check(
      name + ': rail has the same air below it as above',
      b.next && Math.abs(b.next.y - b.rail.bottom - bandPad) < 1,
      b.next ? `gap=${(b.next.y - b.rail.bottom).toFixed(1)}` : 'no band after the head',
    );
    if (b.lane && b.firstKid) {
      check(
        name + ': lane insets its first child by the same rhythm',
        Math.abs(b.firstKid.y - b.lane.y - bandPad) < 1,
        `dy=${(b.firstKid.y - b.lane.y).toFixed(1)}`,
      );
    }
    // A modal with a real foot closes on the foot, not on the panel floor.
    if (b.modalFoot) {
      const lastFootBtn = b.modalFootButtons[b.modalFootButtons.length - 1];
      check(
        name + ': foot closes on the panel edges',
        lastFootBtn &&
          Math.abs(p.right - lastFootBtn.right - modalPad) < 1 &&
          Math.abs(p.bottom - lastFootBtn.bottom - bandPad) < 1,
        lastFootBtn
          ? `right=${(p.right - lastFootBtn.right).toFixed(1)} bottom=${(p.bottom - lastFootBtn.bottom).toFixed(1)}`
          : 'no foot verbs',
      );
      check(
        name + ': bands stop at the foot',
        Math.abs(b.last.bottom - b.modalFoot.y) < 1,
        `gap=${(b.modalFoot.y - b.last.bottom).toFixed(1)}`,
      );
    } else {
      check(
        name + ': last band closes on the panel floor',
        b.last && Math.abs(p.bottom - b.last.bottom) < 1,
        b.last ? `gap=${(p.bottom - b.last.bottom).toFixed(1)}` : 'no bands',
      );
    }
    if (b.footButtons.length) {
      const lastBtn = b.footButtons[b.footButtons.length - 1];
      check(
        name + ': foot verb clears the panel edges',
        Math.abs(p.right - lastBtn.right - modalPad) < 1 && Math.abs(p.bottom - lastBtn.bottom - bandPad) < 1,
        `right=${(p.right - lastBtn.right).toFixed(1)} bottom=${(p.bottom - lastBtn.bottom).toFixed(1)}`,
      );
      check(
        name + ': foot verb has the same air above it as below',
        Math.abs(lastBtn.y - b.foot.y - bandPad) < 1 && Math.abs(b.foot.bottom - lastBtn.bottom - bandPad) < 1,
        `above=${(lastBtn.y - b.foot.y).toFixed(1)} below=${(b.foot.bottom - lastBtn.bottom).toFixed(1)}`,
      );
    }
  });

  // ── Saved keys: one column of readouts ──
  if (mmSecrets) {
    const p = mmSecrets.panel;
    const rows = mmSecrets.rows;
    if (rows.length) {
      checkHeight('secret row', rows[0], [32]);
      const pitches = new Set(rows.slice(1).map((r, i) => r.y - rows[i].y));
      check('secret rows sit on a constant pitch', pitches.size <= 1, `pitches {${[...pitches]}}`);
      check(
        'secret rows ride the modal inset',
        new Set(rows.map((r) => r.x)).size === 1 &&
          Math.abs(p.right - rows[0].right - modalPad) < 1,
        `x {${[...new Set(rows.map((r) => r.x))]}} right=${(p.right - rows[0].right).toFixed(1)}`,
      );
      check(
        'secret titles share one column',
        new Set(mmSecrets.titles.map((t) => t.x)).size === 1,
        `x {${[...new Set(mmSecrets.titles.map((t) => t.x))]}}`,
      );
      check(
        'secret verbs share one right edge and keep the row content edge',
        new Set(mmSecrets.verbs.map((v) => v.right)).size === 1 &&
          rows[0].right - mmSecrets.verbs[0].right === 8,
        `rights {${[...new Set(mmSecrets.verbs.map((v) => v.right))]}} row=${rows[0].right}`,
      );
    }
  }

  // ── Theme customizer: master-detail inside one lane ──
  if (mmTheme && mmTheme.columns.length === 2) {
    const p = mmTheme.panel;
    const [list, editor] = mmTheme.columns;
    check(
      'theme: list column rides the modal inset',
      Math.abs(list.x - p.x - modalPad) < 1,
      `left=${(list.x - p.x).toFixed(1)}`,
    );
    check(
      'theme: editor column rides the modal inset',
      Math.abs(p.right - editor.right - modalPad) < 1,
      `right=${(p.right - editor.right).toFixed(1)}`,
    );
    check(
      'theme: both columns share the lane top',
      Math.abs(list.y - editor.y) < 1,
      `list=${list.y} editor=${editor.y}`,
    );
  }

  if (mmFoot) {
    const p = mmFoot.panel;
    if (mmFoot.tabBar) {
      check('modal tab strip bleeds to the panel edges', mmFoot.tabBar.x === p.x && mmFoot.tabBar.width === p.width);
    }
    (mmFoot.fieldPairs || []).forEach((pair, i) => {
      const fc = pair.field.y + pair.field.height / 2;
      const cc = pair.ctrl.y + pair.ctrl.height / 2;
      check(
        `field/control pair ${i} shares one centre line`,
        Math.abs(fc - cc) < 0.75,
        `field ${pair.field.height}@${pair.field.y} vs control ${pair.ctrl.height}@${pair.ctrl.y}`,
      );
    });
    if (mmFoot.foot && mmFoot.footButtons.length) {
      const last = mmFoot.footButtons[mmFoot.footButtons.length - 1];
      check(
        'modal foot closes on the panel edges',
        p.right - last.right === modalPad && p.bottom - last.bottom === bandPad,
        `right=${p.right - last.right} bottom=${p.bottom - last.bottom}`,
      );
      check(
        'modal foot verb has the same air above it as below',
        Math.abs(last.y - mmFoot.foot.y - bandPad) < 1 && Math.abs(mmFoot.foot.bottom - last.bottom - bandPad) < 1,
        `above=${(last.y - mmFoot.foot.y).toFixed(1)} below=${(mmFoot.foot.bottom - last.bottom).toFixed(1)}`,
      );
      checkHeight('modal foot button', last, [28]);
    }
  }

  // ── Every modal: no box measures a fractional height ──
  check(
    'no modal box has a fractional height',
    offbeat.length === 0,
    offbeat.map((o) => `${o.state}:${o.el}=${o.height}`).join(' '),
  );

  console.log(`\n${checks - failures}/${checks} checks passed, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})().catch((e) => {
  console.error('grid audit crashed:', e.message);
  process.exit(2);
});
