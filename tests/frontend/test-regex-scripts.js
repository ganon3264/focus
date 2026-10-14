// Unit tests for regex-scripts.js — row editing glue (flags, placement,
// mode, enable toggle, expand, preview request shape).
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;

var path = require('path');
var fs = require('fs');
var realSetTimeout = global.setTimeout;

var env = h.setupBrowserGlobals(global);
var doc = env.document;

var fetchMock = h.createMockFetch({
  ok: true,
  json: function () { return Promise.resolve({ result: 'PREVIEW-OK' }); },
});
global.fetch = fetchMock;
global.Sortable = function () {};

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'features', 'regex-scripts.js'), 'utf8'));

function buildItem(id) {
  var item = h.makeElement('div');
  item.classList.add('regex-item');
  item.dataset.id = id;
  var title = h.makeElement('div');
  title.classList.add('arranger-title-group');
  var toggle = h.makeElement('div');
  toggle.classList.add('arranger-toggle');
  toggle.classList.add('active');
  var body = h.makeElement('div');
  body.classList.add('regex-body');
  body.style = { display: 'none' };

  function field(cls, value) {
    var el = h.makeElement('input');
    el.classList.add(cls);
    el.value = value;
    return el;
  }
  function chip(cls, key, val, active) {
    var el = h.makeElement('button');
    el.classList.add(cls);
    el.dataset[key] = val;
    if (active) el.classList.add('active');
    return el;
  }

  var flagI = chip('regex-flag', 'flag', 'i', true);
  var flagM = chip('regex-flag', 'flag', 'm', false);
  var placeAi = chip('regex-placement', 'place', 'ai', true);
  var placeUser = chip('regex-placement', 'place', 'user', false);
  var promptChip = chip('regex-prompt', 'field', 'apply_prompt', true);
  var displayChip = chip('regex-display', 'field', 'apply_display', true);
  var blockChip = chip('regex-block', 'field', 'as_block', false);
  var pattern = field('regex-pattern', 'a');
  var replacement = field('regex-replacement', 'b');
  var sample = field('regex-sample', 'aaa');
  var out = h.makeElement('div');
  out.classList.add('regex-preview-out');

  item.appendChild(title);
  item.appendChild(toggle);
  item.appendChild(body);
  [
    flagI, flagM, placeAi, placeUser, promptChip, displayChip, blockChip,
    pattern, replacement, sample, out,
  ].forEach(function (c) { body.appendChild(c); });
  doc.body.appendChild(item);
  return {
    item: item, title: title, toggle: toggle, body: body,
    flagI: flagI, flagM: flagM, placeAi: placeAi,
    promptChip: promptChip, displayChip: displayChip, blockChip: blockChip, out: out,
  };
}

// ── flags ────────────────────────────────────────────────────────────────
(function () {
  fetchMock._reset();
  var t = buildItem('s-flags');
  window.handleRegexFlags(t.flagI);
  var call = fetchMock._last();
  assertEqual(call.url, '/api/regex-scripts/s-flags', 'flags PATCH hits correct url');
  assertDeepEqual(JSON.parse(call.opts.body), { flags: 'i' }, 'only active flags sent');
})();

// ── flag toggle ──────────────────────────────────────────────────────────
(function () {
  fetchMock._reset();
  var t = buildItem('s-flag-toggle');
  window.toggleRegexFlag(t.flagM);
  assert(t.flagM.classList.contains('active'), 'toggled chip becomes active');
  assertDeepEqual(JSON.parse(fetchMock._last().opts.body), { flags: 'im' }, 'toggled flag added');
})();

// ── placement ────────────────────────────────────────────────────────────
(function () {
  fetchMock._reset();
  var t = buildItem('s-place');
  window.handleRegexPlacement(t.placeAi);
  assertDeepEqual(JSON.parse(fetchMock._last().opts.body), { placement: 'ai' }, 'only active placements sent');
})();

// ── enable toggle ────────────────────────────────────────────────────────
(function () {
  fetchMock._reset();
  var t = buildItem('s-enabled');
  assert(t.toggle.classList.contains('active'), 'toggle starts active');
  window.handleRegexEnabled(t.toggle);
  assert(!t.toggle.classList.contains('active'), 'toggle flips off immediately');
  assertDeepEqual(JSON.parse(fetchMock._last().opts.body), { enabled: false }, 'enabled=false sent');
})();

// ── expand / collapse ────────────────────────────────────────────────────
(function () {
  var t = buildItem('s-expand');
  assertEqual(t.body.style.display, 'none', 'body starts hidden');
  window.toggleRegexBody(t.title);
  assertEqual(t.body.style.display, 'block', 'body expands on toggle');
  assert(t.item.classList.contains('expanded'), 'item marked expanded');
  window.toggleRegexBody(t.title);
  assertEqual(t.body.style.display, 'none', 'body collapses on second toggle');
  assert(!t.item.classList.contains('expanded'), 'expanded marker removed');
})();

// ── preview ──────────────────────────────────────────────────────────────
(function () {
  fetchMock._reset();
  var t = buildItem('s-preview');
  window.previewRegexScript(t.item.querySelector('.regex-pattern'));
  var call = fetchMock._last();
  assertEqual(call.url, '/api/regex-scripts/preview', 'preview hits preview endpoint');
  assertDeepEqual(
    JSON.parse(call.opts.body),
    { pattern: 'a', replacement: 'b', flags: 'i', sample: 'aaa', as_block: false, name: 'Block' },
    'preview payload carries pattern/replacement/flags/sample/block/name'
  );
  realSetTimeout(function () {
    assertEqual(t.out.textContent, 'PREVIEW-OK', 'preview result written to output');
    h.printSummary();
  }, 0);
})();
