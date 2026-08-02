// Unit tests for theme-manager.js — dark/light slots, palette resolution, CRUD
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

var globals = h.setupBrowserGlobals(global);

var SLATE = {
  '--bg': '#0b0d10',
  '--surface': '#13151a',
  '--accent': '#6366f1',
  '--text': '#f1f3f5',
};
var LIGHT = {
  '--bg': '#f8fafc',
  '--surface': '#ffffff',
  '--accent': '#4f46e5',
  '--text': '#0f172a',
};
var MIDNIGHT = {
  '--bg': '#000000',
  '--surface': '#090909',
  '--accent': '#3b82f6',
  '--text': '#ffffff',
};

global.THEMES = [
  { id: 'builtin-slate', name: 'Slate (Default)', colors: SLATE, is_system: true },
  { id: 'builtin-midnight', name: 'Midnight (OLED)', colors: MIDNIGHT, is_system: true },
  { id: 'builtin-light', name: 'Light', colors: LIGHT, is_system: true },
  { id: 'custom-1', name: 'My Theme', colors: SLATE, is_system: false },
];
global.THEME_STATE = {
  dark_theme_id: 'builtin-slate',
  light_theme_id: 'builtin-light',
  char_theme_id: null,
  char_name: null,
};

// Controllable matchMedia mock (default: dark)
var _dark = true;
global.matchMedia = function () {
  return { matches: _dark, addEventListener: function () {}, addListener: function () {} };
};

// Toast capture
var _toasts = [];
global.showInfoToast = function (m) { _toasts.push(m); };

// documentElement with style.setProperty capture
var styleSet = {};
global.document.documentElement = {
  style: {
    setProperty: function (k, v) { styleSet[k] = v; },
  },
};

// Color picker mock for editor tests
var colorInput = makeElement('input');
colorInput.setAttribute('type', 'color');
colorInput.setAttribute('data-var', '--accent');
colorInput.value = '#6366f1';
global.document._body.appendChild(colorInput);
global.document.getElementById = function () { return null; };
global.document.querySelector = function (sel) {
  if (sel === 'input[data-var="--accent"]') return colorInput;
  return null;
};
global.document.querySelectorAll = function (sel) {
  if (sel === '#theme-color-pickers input[type="color"]') return [colorInput];
  return [];
};

// Confirm modal mock
global.openConfirmModal = function () {};
global.closeModal = function () {};

// Load module — exports bare functions
var src = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'theme-manager.js'), 'utf8');
eval(src + '\nwindow.hexToRgb=hexToRgb;window.lightenHex=lightenHex;window.computeAccentDerivatives=computeAccentDerivatives;window.resolvePalette=resolvePalette;');

// ── hexToRgb ──
(function () {
  var r = hexToRgb('#6366f1');
  assertEqual(r.r, 99, 'hexToRgb: red');
  assertEqual(r.g, 102, 'hexToRgb: green');
  assertEqual(r.b, 241, 'hexToRgb: blue');
})();

// ── hexToRgb without # ──
(function () {
  var r = hexToRgb('6366f1');
  assertEqual(r.r, 99, 'hexToRgb without #: red');
})();

// ── hexToRgb invalid returns null ──
(function () {
  assertEqual(hexToRgb('invalid'), null, 'hexToRgb invalid returns null');
  assertEqual(hexToRgb('#xyz'), null, 'hexToRgb short invalid returns null');
})();

// ── lightenHex ──
(function () {
  var l = lightenHex('#6366f1', 15);
  assert(l.length === 7 && l[0] === '#', 'lightenHex returns valid hex');
  assert(l !== '#6366f1', 'lightenHex changes the color');
})();

// ── lightenHex with invalid returns original ──
(function () {
  assertEqual(lightenHex('invalid', 15), 'invalid', 'lightenHex invalid returns input');
})();

// ── computeAccentDerivatives ──
(function () {
  var d = computeAccentDerivatives('#6366f1');
  assertEqual(d['--accent-hover'].length, 7, 'accent-hover is hex color');
  assert(d['--accent-dim'].indexOf('rgba') >= 0, 'accent-dim is rgba');
  assert(d['--accent-faint'].indexOf('rgba') >= 0, 'accent-faint is rgba');
})();

// ── Module load applies dark slot (dark scheme → slate) ──
(function () {
  assertEqual(styleSet['--bg'], SLATE['--bg'], 'module load: dark scheme → dark slot colors');
  assertEqual(styleSet['--accent-hover'], lightenHex(SLATE['--accent'], 15), 'module load: accent-hover derived');
})();

// ── setSlot dark persists + applies ──
(function () {
  globals.fetch._reset();
  _toasts.length = 0;
  window.setSlot('dark', 'builtin-midnight');
  assertEqual(styleSet['--bg'], MIDNIGHT['--bg'], 'setSlot dark: dark scheme now midnight');
  var last = globals.fetch._last();
  assertEqual(last.url, '/api/settings/theme', 'setSlot: PUT settings/theme');
  assertDeepEqual(JSON.parse(last.opts.body), { slot: 'dark', theme_id: 'builtin-midnight' }, 'setSlot: body');
  assertEqual(_toasts.length, 1, 'setSlot: toast shown');
  window.setSlot('dark', 'builtin-slate');
})();

// ── setSlot light applies in light scheme ──
(function () {
  _dark = false;
  window.setSlot('light', 'builtin-slate');
  assertEqual(styleSet['--bg'], SLATE['--bg'], 'setSlot light + light scheme: slate applied');
  window.setSlot('light', 'builtin-light');
  _dark = true;
})();

// ── cache stores both slot palettes for pre-paint ──
(function () {
  var cached = JSON.parse(globals.localStorage.getItem('focus-theme-state'));
  assertEqual(cached.darkId, 'builtin-slate', 'cache: darkId');
  assertEqual(cached.lightId, 'builtin-light', 'cache: lightId');
  assertDeepEqual(cached.darkColors, SLATE, 'cache: darkColors');
  assertDeepEqual(cached.lightColors, LIGHT, 'cache: lightColors');
})();

// ── legacy cache key removed on apply ──
(function () {
  globals.localStorage.setItem('focus-custom-theme', '{"--bg":"#000"}');
  window.reapplyTheme();
  assertEqual(globals.localStorage.getItem('focus-custom-theme'), null, 'legacy focus-custom-theme removed');
})();

// ── effectiveThemeId follows scheme ──
(function () {
  _dark = true;
  assertEqual(window.effectiveThemeId(), 'builtin-slate', 'effective dark scheme: dark slot');
  _dark = false;
  assertEqual(window.effectiveThemeId(), 'builtin-light', 'effective light scheme: light slot');
})();

// ── effectiveThemeId: character override wins ──
(function () {
  _dark = true;
  window.THEME_STATE.char_theme_id = 'builtin-midnight';
  assertEqual(window.effectiveThemeId(), 'builtin-midnight', 'effective: char theme wins');
  window.THEME_STATE.char_theme_id = null;
})();

// ── resolvePalette includes accent derivatives ──
(function () {
  var palette = resolvePalette(window.getTheme('builtin-slate'));
  assertEqual(palette['--bg'], SLATE['--bg'], 'resolvePalette: colors copied');
  assert(palette['--accent-hover'], 'resolvePalette: accent-hover derived');
})();

// ── saveTheme: create (POST) vs update (PATCH), no light field ──
(function () {
  var calls = [];
  global.fetch = function (url, opts) {
    calls.push({ url: url, opts: opts });
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ id: 'new-id' }); } });
  };
  var done1 = null, done2 = null;
  window.saveTheme('New', SLATE, null, function (ok, id) { done1 = [ok, id]; });
  return Promise.resolve().then(function () {
    window.saveTheme('New', SLATE, 'custom-1', function (ok, id) { done2 = [ok, id]; });
  }).then(function () {
    return Promise.resolve();
  }).then(function () {
    assertEqual(calls[0].url, '/api/themes', 'saveTheme create: POST /api/themes');
    assertEqual(calls[0].opts.method, 'POST', 'saveTheme create: method POST');
    assertDeepEqual(JSON.parse(calls[0].opts.body), { name: 'New', colors: SLATE }, 'saveTheme create: no light in body');
    assertEqual(calls[1].url, '/api/themes/custom-1', 'saveTheme update: PATCH /api/themes/custom-1');
    assertEqual(calls[1].opts.method, 'PATCH', 'saveTheme update: method PATCH');
    assertEqual(done1[0], true, 'saveTheme create callback ok');
    assertEqual(done1[1], 'new-id', 'saveTheme create callback id');
  });
})();

// ── resetTheme ──
(function () {
  var called = null;
  global.fetch = function (url, opts) {
    called = { url: url, method: opts.method };
    return Promise.resolve({ ok: true });
  };
  window.resetTheme('builtin-slate', function (ok) { assert(ok, 'resetTheme callback ok'); });
  assertEqual(called.url, '/api/themes/builtin-slate/reset', 'resetTheme: url');
  assertEqual(called.method, 'POST', 'resetTheme: method');
})();

// ── deleteTheme ──
(function () {
  var called = null;
  global.fetch = function (url, opts) {
    called = { url: url, method: opts.method };
    return Promise.resolve({ ok: true });
  };
  window.deleteTheme('custom-1', function (ok) { assert(ok, 'deleteTheme callback ok'); });
  assertEqual(called.url, '/api/themes/custom-1', 'deleteTheme: url');
  assertEqual(called.method, 'DELETE', 'deleteTheme: method');
})();

// ── refreshThemes refetches list ──
(function () {
  global.fetch = function (url) {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve([{ id: 'only' }]); } });
  };
  window.refreshThemes(function () {
    assertEqual(window.THEMES.length, 1, 'refreshThemes: THEMES replaced');
  });
})();

// ── themeModalState: init selects effective theme ──
(function () {
  global.fetch = function (url, opts) {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ id: 'x' }); } });
  };
  var state = window.themeModalState();
  state.init();
  assertEqual(state.themes.length, 4, 'modal: themes listed');
  assertEqual(state.selectedId, 'builtin-slate', 'modal: effective theme selected');
  assertEqual(state.selectedIsSystem, true, 'modal: selected is system');
  assertEqual(state.darkId, 'builtin-slate', 'modal: darkId tracked');
  assertEqual(state.lightId, 'builtin-light', 'modal: lightId tracked');
})();

// ── themeModalState: select loads editor ──
(function () {
  var state = window.themeModalState();
  state.init();
  assertEqual(state.themes.length, 4, 'modal: themes listed');
  assertEqual(state.selectedId, 'builtin-slate', 'modal: effective theme selected');
  assertEqual(state.selectedIsSystem, true, 'modal: selected is system');
  assertEqual(state.darkId, 'builtin-slate', 'modal: darkId tracked');
  assertEqual(state.lightId, 'builtin-light', 'modal: lightId tracked');
  state.select('custom-1');
  assertEqual(state.selectedId, 'custom-1', 'modal: custom selected');
  assertEqual(state.selectedIsSystem, false, 'modal: custom not system');
  assertEqual(state.editName, 'My Theme', 'modal: name loaded');
  assertEqual(colorInput.value, '#6366f1', 'modal: picker loaded from theme colors');
})();

// ── themeModalState: create without a name notifies, no request ──
(function () {
  var fetches = [];
  global.fetch = function (url, opts) {
    fetches.push({ url: url, opts: opts });
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ id: 'x' }); } });
  };
  _toasts.length = 0;
  var state = window.themeModalState();
  state.init();
  state.editName = '';
  state.create();
  assertEqual(fetches.length, 0, 'modal create: no request without name');
  assertEqual(_toasts.length, 1, 'modal create: toast shown');
  assertEqual(_toasts[0], 'Enter a theme name first', 'modal create: toast text');
})();

// ── Confirm modal capture ──
var _confirmCalls = [];
global.openConfirmModal = function (message, cb) {
  _confirmCalls.push({ message: message, cb: cb });
};

// ── themeModalState: dirty tracking ──
(function () {
  var state = window.themeModalState();
  state.init();
  state.select('custom-1');
  assertEqual(state.dirty, false, 'dirty: clean after select');
  colorInput.value = '#111111';
  state.markDirty();
  assertEqual(state.dirty, true, 'dirty: color change marks dirty');
  colorInput.value = '#6366f1';
  state.markDirty();
  assertEqual(state.dirty, false, 'dirty: revert to stored color clears');
  state.editName = 'Renamed';
  state.markDirty();
  assertEqual(state.dirty, true, 'dirty: name change marks dirty');
  state.editName = 'My Theme';
  state.markDirty();
  assertEqual(state.dirty, false, 'dirty: revert name clears');
})();

// ── themeModalState: switchTo with unsaved changes prompts ──
(function () {
  var state = window.themeModalState();
  state.init();
  state.select('custom-1');
  colorInput.value = '#111111';
  state.markDirty();
  _confirmCalls.length = 0;
  state.switchTo('builtin-midnight');
  assertEqual(state.selectedId, 'custom-1', 'switchTo dirty: stays on current theme');
  assertEqual(_confirmCalls.length, 1, 'switchTo dirty: confirm shown');
  assert(_confirmCalls[0].message.indexOf('custom') >= 0 || _confirmCalls[0].message.indexOf('My Theme') >= 0, 'switchTo dirty: message names theme');
  _confirmCalls[0].cb();
  assertEqual(state.selectedId, 'builtin-midnight', 'switchTo dirty: confirm discards and switches');
  assertEqual(state.dirty, false, 'switchTo dirty: clean after switch');
})();

// ── themeModalState: switchTo clean switches without prompt ──
(function () {
  var state = window.themeModalState();
  state.init();
  state.select('custom-1');
  _confirmCalls.length = 0;
  state.switchTo('builtin-midnight');
  assertEqual(_confirmCalls.length, 0, 'switchTo clean: no confirm');
  assertEqual(state.selectedId, 'builtin-midnight', 'switchTo clean: switched');
})();

// ── themeModalState: save resets dirty ──
(function () {
  global.fetch = function (url, opts) {
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ id: 'custom-1' }); } });
  };
  var state = window.themeModalState();
  state.init();
  state.select('custom-1');
  colorInput.value = '#111111';
  state.markDirty();
  state.save();
  return new Promise(function (res) { setImmediate(res); }).then(function () {
    assertEqual(state.dirty, false, 'save: dirty cleared after save');
  });
})();

// ── themeModalState: create makes the theme immediately ──
(function () {
  var created = null;
  global.fetch = function (url, opts) {
    if (opts && opts.method === 'POST') {
      created = JSON.parse(opts.body);
      return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ id: 'new-id' }); } });
    }
    return Promise.resolve({ ok: true, json: function () {
      return Promise.resolve([
        { id: 'builtin-slate', name: 'Slate (Default)', colors: SLATE, is_system: true },
        { id: 'builtin-midnight', name: 'Midnight (OLED)', colors: MIDNIGHT, is_system: true },
        { id: 'builtin-light', name: 'Light', colors: LIGHT, is_system: true },
        { id: 'custom-1', name: 'My Theme', colors: SLATE, is_system: false },
        { id: 'new-id', name: 'Mint', colors: { '--accent': '#abcdef' }, is_system: false },
      ]);
    } });
  };
  _toasts.length = 0;
  var state = window.themeModalState();
  state.init();
  state.editName = 'Mint';
  colorInput.value = '#abcdef';
  state.create();
  assertDeepEqual(created, { name: 'Mint', colors: { '--accent': '#abcdef' } }, 'modal create: POST payload');
  return new Promise(function (res) { setImmediate(res); }).then(function () {
    assertEqual(_toasts[0], 'Theme "Mint" created', 'modal create: toast text');
    assertEqual(state.selectedId, 'new-id', 'modal create: new theme selected for editing');
    assertEqual(state.editName, 'Mint', 'modal create: name loaded');
  });
})();

// ── themeModalState: save without a name notifies instead of saving ──
(function () {
  var fetches = [];
  global.fetch = function (url, opts) {
    fetches.push({ url: url, opts: opts });
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ id: 'x' }); } });
  };
  _toasts.length = 0;
  var state = window.themeModalState();
  state.init();
  state.editName = '';
  state.save();
  assertEqual(fetches.length, 0, 'modal save: no request without name');
  assertEqual(_toasts.length, 1, 'modal save: toast shown');
  assertEqual(_toasts[0], 'Enter a theme name first', 'modal save: toast text');
})();

// ── themeModalState: save updates selected theme in place ──
(function () {
  var saved = null;
  global.fetch = function (url, opts) {
    if (url === '/api/themes/custom-1') saved = JSON.parse(opts.body);
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ id: 'custom-1' }); } });
  };
  var state = window.themeModalState();
  state.init();
  state.select('custom-1');
  state.editName = 'Renamed';
  colorInput.value = '#111111';
  state.save();
  assertDeepEqual(saved, { name: 'Renamed', colors: { '--accent': '#111111' } }, 'modal save update: payload');
})();

// ── Result ──
h.printSummary();
