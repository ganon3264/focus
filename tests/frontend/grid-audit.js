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
      preset: one('#preset-selector .field'),
      newChat: one('.right-sidebar .sidebar-section > .btn'),
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
  await browser.close();

  const inset = 12;

  checkGrid('left pane', m.leftPane);
  checkGrid('right pane', m.rightPane);
  [...m.leftTitles, ...m.rightTitles].forEach((r, i) => checkGrid('rail ' + i, r));
  [...m.leftSections].forEach((r, i) => checkGrid('left section ' + i, r));
  checkGrid('preset well', m.preset);
  checkGrid('new chat', m.newChat);
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
  if (m.preset) checkInset('preset well', m.preset, m.leftPane, inset);
  if (m.newChat) checkInset('new chat', m.newChat, m.rightPane, inset);

  if (m.leftTitles.length && m.rightTitles.length) {
    checkSameRow('pane rails', [m.leftTitles[0], m.rightTitles[0]]);
  }
  if (m.preset && m.newChat) {
    checkSameRow('first control row', [m.preset, m.newChat]);
    check(
      'New Chat and the preset well are the same box',
      m.newChat.height === m.preset.height && m.newChat.y === m.preset.y,
      `new chat ${m.newChat.height}@${m.newChat.y} vs preset ${m.preset.height}@${m.preset.y}`,
    );
  }
  checkHeight('preset well', m.preset, [28, 32]);
  checkHeight('new chat', m.newChat, [28, 32]);
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

  console.log(`\n${checks - failures}/${checks} checks passed, ${failures} failed`);
  process.exit(failures ? 1 : 0);
})().catch((e) => {
  console.error('grid audit crashed:', e.message);
  process.exit(2);
});
