// Unit tests for theme_manager.js — color math and theme application
var h = require('./_helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

var storage = {};
global.localStorage = {
  _store: storage,
  getItem: function (k) { return storage.hasOwnProperty(k) ? storage[k] : null; },
  setItem: function (k, v) { storage[k] = String(v); },
  removeItem: function (k) { delete storage[k]; },
  clear: function () { storage = {}; },
};
global.document = h.createMockDocument();
global.document.documentElement = { style: {} };
global.window = global;
global.fetch = function () { return Promise.resolve({ ok: true }); };
global.getComputedStyle = function () {
  return { getPropertyValue: function () { return '#000000'; } };
};
global.closeModal = function () {};

// Add theme-color-pickers input for preview/save tests
var colorInput = makeElement('input');
colorInput.type = 'color';
colorInput.setAttribute('data-var', '--accent');
colorInput.value = '#6366f1';
global.document._body.appendChild(colorInput);
global.document.getElementById = function (id) { return null; };
global.document.querySelector = function (sel) {
  if (sel === '[onclick="openModal(\'modal-themes\')"]') return null;
  if (sel === 'input[data-var="--accent"]') return colorInput;
  return null;
};
global.document.querySelectorAll = function (sel) {
  if (sel === '#theme-color-pickers input[type="color"]') return [colorInput];
  return [];
};

// Load module — exports bare functions
var src = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'theme_manager.js'), 'utf8');
eval(src + '\nwindow.hexToRgb=hexToRgb;window.lightenHex=lightenHex;window.computeAccentDerivatives=computeAccentDerivatives;window.applyPresetTheme=applyPresetTheme;window.resetThemePreview=resetThemePreview;window.saveCustomTheme=saveCustomTheme;');

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

// ── computeAccentDerivatives invalid returns empty ──
(function () {
  var d = computeAccentDerivatives('invalid');
  assertDeepEqual(d, {}, 'computeAccentDerivatives invalid returns empty');
})();

// ── applyPresetTheme sets CSS vars and localStorage ──
(function () {
  var styleSet = [];
  var rootStyle = global.document.documentElement.style;
  rootStyle.setProperty = function (k, v) { styleSet.push(k); };

  applyPresetTheme('midnight');
  assert(styleSet.indexOf('--accent') >= 0, 'midnight: --accent set');
  assert(styleSet.indexOf('--bg') >= 0, 'midnight: --bg set');
  assert(storage['focus-custom-theme'], 'midnight: persisted to localStorage');
})();

// ── applyPresetTheme updates color input value ──
(function () {
  var oldValue = colorInput.value;
  applyPresetTheme('light');
  assertEqual(colorInput.value, '#4f46e5', 'light theme: color picker updated');
  colorInput.value = oldValue;
})();

// ── resetThemePreview with stored theme restores vars ──
(function () {
  storage['focus-custom-theme'] = JSON.stringify({ '--accent': '#ff0000' });
  var restoredKeys = [];
  global.document.documentElement.style.setProperty = function (k) { restoredKeys.push(k); };
  resetThemePreview();
  assert(restoredKeys.indexOf('--accent') >= 0, 'resetThemePreview restores --accent');
  delete storage['focus-custom-theme'];
})();

// ── saveCustomTheme persists new theme ──
(function () {
  global.document.querySelectorAll = function (sel) {
    if (sel === '#theme-color-pickers input[type="color"]') return [colorInput];
    return [];
  };

  var savedTheme = null;
  var oldFetch = global.fetch;
  global.fetch = function (url, opts) {
    savedTheme = JSON.parse(opts.body);
    return Promise.resolve({ ok: true });
  };

  saveCustomTheme();
  assert(!!savedTheme, 'saveCustomTheme fetch called');
  if (savedTheme) {
    assertEqual(savedTheme.key, 'theme_json', 'saveCustomTheme: key is theme_json');
  }
  global.fetch = oldFetch;
})();

// ── Result ──
h.printSummary();
