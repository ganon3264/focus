// Unit tests for skin-manager.js — skin registry, persistence, attribute swap
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var path = require('path');
var fs = require('fs');

var globals = h.setupBrowserGlobals(global);

// Toast capture
var _toasts = [];
global.showToast = function (msg) { _toasts.push(msg); };

var src = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'skin-manager.js'), 'utf8');
eval(src);

function lastSkinEvent() {
  return global._dispatchedEvents.filter(function (e) { return e.type === 'skin-changed'; }).pop() || null;
}

// ── Registry ──
(function () {
  var ids = global.SKINS.map(function (s) { return s.id; });
  assert(ids.indexOf('instrument') !== -1, 'registry contains instrument');
  assert(ids.indexOf('classic') !== -1, 'registry contains classic');
  global.SKINS.forEach(function (s) {
    assert(s.label && s.description, 'skin ' + s.id + ' has label and description');
  });
})();

// ── get() ──
(function () {
  assertEqual(global.SkinManager.get(), 'classic', 'empty storage defaults to classic');

  global.localStorage.setItem('focus-skin', 'bogus');
  assertEqual(global.SkinManager.get(), 'classic', 'unknown stored skin falls back to classic');

  global.localStorage.setItem('focus-skin', 'classic');
  assertEqual(global.SkinManager.get(), 'classic', 'get() reads the stored skin');
  global.localStorage.clear();
})();

// ── set() ──
(function () {
  global._dispatchedEvents.length = 0;
  _toasts.length = 0;
  global.SkinManager.set('classic');

  assertEqual(global.document.documentElement.getAttribute('data-skin'), 'classic', 'set() writes data-skin attribute');
  assertEqual(global.localStorage.getItem('focus-skin'), 'classic', 'set() persists the choice');

  var ev = lastSkinEvent();
  assert(ev, 'set() dispatches skin-changed');
  assertEqual(ev && ev.detail && ev.detail.id, 'classic', 'skin-changed carries the skin id');
  assertEqual(_toasts.length, 1, 'set() shows exactly one toast');
})();

// ── set() invalid ──
(function () {
  global._dispatchedEvents.length = 0;
  _toasts.length = 0;
  global.SkinManager.set('bogus');

  assertEqual(global.document.documentElement.getAttribute('data-skin'), 'classic', 'invalid set() leaves attribute alone');
  assertEqual(global.localStorage.getItem('focus-skin'), 'classic', 'invalid set() does not persist');
  assertEqual(lastSkinEvent(), null, 'invalid set() dispatches nothing');
  assertEqual(_toasts.length, 0, 'invalid set() toasts nothing');
})();

// ── set() switches to the opt-in skin and back ──
(function () {
  global.SkinManager.set('instrument');
  assertEqual(global.document.documentElement.getAttribute('data-skin'), 'instrument', 'set() applies the opt-in skin');
  assertEqual(global.localStorage.getItem('focus-skin'), 'instrument', 'opt-in skin is persisted');

  global.SkinManager.set('classic');
  assertEqual(global.document.documentElement.getAttribute('data-skin'), 'classic', 'set() restores the default skin');
})();

// ── apply() ──
(function () {
  global.localStorage.setItem('focus-skin', 'classic');
  global.document.documentElement.setAttribute('data-skin', 'instrument');
  global.SkinManager.apply();
  assertEqual(global.document.documentElement.getAttribute('data-skin'), 'classic', 'apply() re-applies the stored skin');
})();

// ── Result ──
h.printSummary();
