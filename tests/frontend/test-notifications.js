// Unit tests for notifications.js — toast queue, variants, timers, cap
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertIncludes = h.assertIncludes;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

h.setupBrowserGlobals(global);

// Patch createElement to add listener support (mock elements have none)
var _origCreate = global.document.createElement;
global.document.createElement = function (tag) {
  var el = _origCreate(tag);
  el._listeners = {};
  el.addEventListener = function (name, fn) {
    (el._listeners[name] = el._listeners[name] || []).push(fn);
  };
  el.removeEventListener = function (name, fn) {
    var list = el._listeners[name] || [];
    var idx = list.indexOf(fn);
    if (idx >= 0) list.splice(idx, 1);
  };
  return el;
};

// Deterministic timers
var timers = [];
global.setTimeout = function (fn, ms) {
  var t = { fn: fn, ms: ms, cleared: false };
  timers.push(t);
  return t;
};
global.clearTimeout = function (t) {
  if (t) t.cleared = true;
};
function pendingCount() {
  return timers.filter(function (t) { return !t.cleared; }).length;
}
function flushTimers(pred) {
  var guard = 0;
  while (guard++ < 100) {
    var pending = timers.filter(function (t) { return !t.cleared && (!pred || pred(t)); });
    if (!pending.length) return;
    pending.forEach(function (t) { t.cleared = true; });
    pending.forEach(function (t) { t.fn(); });
  }
}
function flushRemovals() {
  flushTimers(function (t) { return t.ms === 220; });
}
function resetTimers() { timers.length = 0; }

global.navigator = global.navigator || {};
global.getSvgSprite = function () { return '<svg></svg>'; };

var src = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'notifications.js'), 'utf8');
eval(src);

// ── No container: no-op, no throw ──
(function () {
  var realGet = global.document.getElementById;
  global.document.getElementById = function () { return null; };
  var r = window.showToast('nope');
  assertEqual(r, null, 'showToast without container returns null');
  window.showErrorToast('boom');
  window.hideErrorToast();
  global.document.getElementById = realGet;
})();

// Seed the toast container
var container = makeElement('div');
container.id = 'toast-container';
global.document.body.appendChild(container);

// ── Basic info toast ──
(function () {
  resetTimers();
  window.showToast('Hello');
  assertEqual(container.children.length, 1, 'basic: one card appended');
  var card = container.children[0];
  assert(card.classList.contains('toast'), 'basic: has toast class');
  assert(card.classList.contains('toast-info'), 'basic: info variant');
  assertEqual(card.getAttribute('role'), 'status', 'basic: role status');
  assertEqual(card.dataset.toastType, 'info', 'basic: dataset type');
  var text = card.querySelector('.toast-text');
  assert(text && text.textContent === 'Hello', 'basic: text set');
  assertEqual(pendingCount(), 1, 'basic: auto-dismiss timer armed');
})();

// ── Success variant ──
(function () {
  resetTimers();
  window.showSuccessToast('Saved');
  var card = container.children[container.children.length - 1];
  assert(card.classList.contains('toast-success'), 'success: variant class');
  assertEqual(card.getAttribute('role'), 'status', 'success: role status');
})();

// ── Error variant: persistent, alert role, actions ──
(function () {
  resetTimers();
  window.showErrorToast('Boom');
  var card = container.children[container.children.length - 1];
  assert(card.classList.contains('toast-error'), 'error: variant class');
  assertEqual(card.getAttribute('role'), 'alert', 'error: role alert');
  assertEqual(pendingCount(), 0, 'error: no auto-dismiss timer');
  var actions = card.querySelector('.toast-actions');
  assert(actions, 'error: actions present');
  var btns = actions.querySelectorAll('.toast-btn');
  assertEqual(btns.length, 2, 'error: copy + close buttons');
})();

// ── Queue: multiple toasts stack in order ──
(function () {
  resetTimers();
  container.children.length = 0;
  window.showInfoToast('first');
  window.showInfoToast('second');
  window.showInfoToast('third');
  assertEqual(container.children.length, 3, 'queue: three stacked');
  assertEqual(container.children[0].querySelector('.toast-text').textContent, 'first', 'queue: order preserved');
  assertEqual(container.children[2].querySelector('.toast-text').textContent, 'third', 'queue: order preserved');
})();

// ── Dedup: same type+message refreshes instead of duplicating ──
(function () {
  resetTimers();
  container.children.length = 0;
  window.showInfoToast('dup');
  var before = pendingCount();
  window.showInfoToast('dup');
  assertEqual(container.children.length, 1, 'dedup: single card');
  assertEqual(pendingCount(), before, 'dedup: timer refreshed, not doubled');
  // different type → new card
  window.showErrorToast('dup');
  assertEqual(container.children.length, 2, 'dedup: type distinguishes');
})();

// ── Cap: oldest evicted beyond MAX_VISIBLE ──
(function () {
  resetTimers();
  container.children.length = 0;
  for (var i = 0; i < 7; i++) window.showInfoToast('msg' + i);
  var active = 0;
  container.children.forEach(function (c) {
    if (!c.classList.contains('toast-leave')) active++;
  });
  assertEqual(active, 5, 'cap: only 5 active');
  assert(container.children[0].classList.contains('toast-leave'), 'cap: oldest evicted');
  flushRemovals();
  assertEqual(container.children.length, 5, 'cap: evicted removed after animation');
})();

// ── Auto-dismiss fades then removes ──
(function () {
  resetTimers();
  container.children.length = 0;
  window.showInfoToast('fleeting');
  flushTimers();
  assertEqual(container.children.length, 0, 'auto-dismiss: card removed');
})();

// ── Hover pause / resume ──
(function () {
  resetTimers();
  container.children.length = 0;
  window.showInfoToast('hover me');
  var card = container.children[0];
  var before = pendingCount();
  card._listeners.mouseenter[0]();
  assertEqual(pendingCount(), before - 1, 'hover: timer paused');
  card._listeners.mouseleave[0]();
  assertEqual(pendingCount(), before, 'hover: timer resumed');
})();

// ── hideErrorToast dismisses only error cards ──
(function () {
  resetTimers();
  container.children.length = 0;
  window.showInfoToast('info1');
  window.showErrorToast('err1');
  window.showErrorToast('err2');
  window.hideErrorToast();
  var remaining = container.children.filter(function (c) { return !c.classList.contains('toast-leave'); });
  assertEqual(remaining.length, 1, 'hideErrorToast: only info remains');
  assertEqual(remaining[0].querySelector('.toast-text').textContent, 'info1', 'hideErrorToast: info untouched');
  flushRemovals();
  assertEqual(container.children.length, 1, 'hideErrorToast: errors removed');
})();

// ── hideAllToasts ──
(function () {
  resetTimers();
  container.children.length = 0;
  window.showInfoToast('a');
  window.showErrorToast('b');
  window.hideAllToasts();
  assertEqual(container.children.filter(function (c) { return !c.classList.contains('toast-leave'); }).length, 0, 'hideAllToasts: all dismissed');
})();

// ── Duration option + error with explicit duration ──
(function () {
  resetTimers();
  var t1 = window.showToast('timed', { type: 'info', duration: 100 });
  assert(t1, 'duration: card returned');
  assertEqual(pendingCount(), 1, 'duration: timer armed');
  resetTimers();
  window.showErrorToast('auto-error', { duration: 4000 });
  assertEqual(pendingCount(), 1, 'duration: error auto-dismiss with explicit duration');
})();

// ── Close button dismisses ──
(function () {
  resetTimers();
  container.children.length = 0;
  window.showErrorToast('close me');
  var card = container.children[0];
  var closeBtn = card.querySelector('.toast-close');
  assert(closeBtn, 'close: button exists');
  closeBtn._listeners.click[0]();
  assert(card.classList.contains('toast-leave'), 'close: card dismissed');
})();

h.printSummary();
