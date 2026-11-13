// Regression test: providers.js must initialise on each providers-modal body
// swap. It used to be loaded from the swapped partial; the housekeeping commit
// moved it to the chat page, so the old load-time setTimeout ran before any
// provider cards existed and balance/sort never initialised.
var h = require('./helpers.js');
var assert = h.assert;
var assertEqual = h.assertEqual;

var path = require('path');
var fs = require('fs');

// ── DOM ──
var doc = h.createMockDocument();
var bodyListeners = {};
doc.body.addEventListener = function (name, fn) {
  (bodyListeners[name] = bodyListeners[name] || []).push(fn);
};

var balanceEl = h.makeElement('div');
balanceEl.id = 'balance-prov1';
var gridEl = h.makeElement('div');
gridEl.id = 'providers-grid';

doc.querySelectorAll = function (sel) {
  if (sel.indexOf('balance-') !== -1) return [balanceEl];
  if (sel.indexOf('entity-row') !== -1) return [];
  return [];
};

global.window = global;
global.document = doc;
global.localStorage = h.createMockLocalStorage();

var fetchCalls = [];
var stallUrls = {};
global.fetch = function (url) {
  fetchCalls.push(url);
  if (stallUrls[url]) return new Promise(function () {});
  return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ balances: [] }); } });
};

global.StateManager = {
  get: function (key) { return key === 'provider_id' ? 'prov1' : null; },
};
global.api = {
  providerBalance: function (id) { return '/api/providers/' + id + '/balance'; },
};
// list-manager.js owns the sort-mode read; the grid carries it as an attribute.
global.listSortMode = function () { return 'az'; };

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'hx-queue.js'), 'utf8'));
// Load module
var src = fs.readFileSync(
  path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'providers.js'),
  'utf8',
);
eval(src);

function fireSwap(id) {
  (bodyListeners['htmx:afterSwap'] || []).forEach(function (fn) {
    fn({ detail: { target: { id: id } } });
  });
}

// ── The afterSwap hook exists and is scoped to the modal body ──
assert((bodyListeners['htmx:afterSwap'] || []).length > 0, 'providers.js registers an htmx:afterSwap hook');

fireSwap('some-other-element');
assertEqual(fetchCalls.length, 0, 'unrelated swaps do not fetch balances');

fireSwap('providers-modal-body-inner');
assertEqual(fetchCalls.length, 1, 'providers-modal-body-inner swap fetches balances');
assertEqual(fetchCalls[0], '/api/providers/prov1/balance', 'balance URL is correct');

// ── Balance bypasses the shared write queue ──
// The readout used to go through hxFetch, so a stalled upstream (NanoGPT timing
// out) held every other request behind it for the whole timeout.
stallUrls['/queued-slow'] = true;
window.hxFetch('/queued-slow');
fetchCalls.length = 0;
fireSwap('providers-modal-body-inner');
assertEqual(fetchCalls.length, 1, 'a stalled queued request does not hold the balance fetch');
assertEqual(fetchCalls[0], '/api/providers/prov1/balance', 'balance fetch still issues');

h.printSummary();
