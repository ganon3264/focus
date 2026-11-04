// Unit tests for core/backend-watch.js — unreachable backend locks the screen,
// the health probe unlocks it, and only network failures trigger a probe.
var h = require('./helpers.js');
var assert = h.assert;
var assertEqual = h.assertEqual;

var path = require('path');
var fs = require('fs');

h.setupBrowserGlobals(global);
global.addEventListener = function () {};

var overlay = h.makeElement('div');
overlay.id = 'backend-offline';
overlay.classList.add('hidden');
var app = h.makeElement('div');
app.id = 'app';
var toasts = h.makeElement('div');
toasts.id = 'toast-container';
document.body.appendChild(app);
document.body.appendChild(overlay);
document.body.appendChild(toasts);

var calls = [];
var nextFetch = null;
global.fetch = function (url) {
  calls.push(url);
  return nextFetch ? nextFetch() : Promise.reject(new TypeError('Failed to fetch'));
};

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'backend-watch.js'), 'utf8'));

function tick() {
  return new Promise(function (resolve) {
    setImmediate(resolve);
  });
}

async function main() {
  // ── A failed probe locks: overlay shown, app inert, one persistent toast.
  calls = [];
  nextFetch = null;
  BackendWatch.check();
  await tick();
  assertEqual(BackendWatch.isOffline(), true, 'failed probe -> offline');
  assert(!overlay.classList.contains('hidden'), 'overlay shown on lock');
  assert(app.hasAttribute('inert'), 'app becomes inert');

  // ── The probe answers again: unlock, restore input, swap the toast.
  nextFetch = function () {
    return Promise.resolve({ ok: true });
  };
  BackendWatch.check();
  await tick();
  assertEqual(BackendWatch.isOffline(), false, 'healthy probe -> online');
  assert(overlay.classList.contains('hidden'), 'overlay hidden on unlock');
  assert(!app.hasAttribute('inert'), 'app inert cleared');

  // ── An aborted request is user intent, not a dead backend.
  calls = [];
  nextFetch = function () {
    var err = new Error('aborted');
    err.name = 'AbortError';
    return Promise.reject(err);
  };
  await window.fetch('/api/chats').catch(function () {});
  await tick();
  assertEqual(calls.length, 1, 'abort does not probe');

  // ── Any other fetch rejection probes the backend.
  calls = [];
  nextFetch = null;
  await window.fetch('/api/chats').catch(function () {});
  await tick();
  assertEqual(calls[1], '/api/health', 'network failure probes health');

  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
