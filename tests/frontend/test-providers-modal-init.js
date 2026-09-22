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
doc.body.addEventListener = function (name, fn) { bodyListeners[name] = fn; };

var balanceEl = h.makeElement('div');
balanceEl.id = 'balance-prov1';
var gridEl = h.makeElement('div');
gridEl.id = 'providers-grid';

doc.querySelectorAll = function (sel) {
  if (sel.indexOf('balance-') !== -1) return [balanceEl];
  if (sel.indexOf('provider-card') !== -1) return [];
  return [];
};

global.window = global;
global.document = doc;
global.localStorage = h.createMockLocalStorage();

var fetchCalls = [];
global.fetch = function (url) {
  fetchCalls.push(url);
  return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ balances: [] }); } });
};

global.StateManager = {
  get: function (key) { return key === 'provider_id' ? 'prov1' : null; },
};
global.api = {
  providerBalance: function (id) { return '/api/providers/' + id + '/balance'; },
};

// Load module
var src = fs.readFileSync(
  path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'providers.js'),
  'utf8',
);
eval(src);

// ── The afterSwap hook exists and is scoped to the modal body ──
assert(typeof bodyListeners['htmx:afterSwap'] === 'function', 'providers.js registers an htmx:afterSwap hook');

bodyListeners['htmx:afterSwap']({ detail: { target: { id: 'some-other-element' } } });
assertEqual(fetchCalls.length, 0, 'unrelated swaps do not fetch balances');

bodyListeners['htmx:afterSwap']({ detail: { target: { id: 'providers-modal-body-inner' } } });
assertEqual(fetchCalls.length, 1, 'providers-modal-body-inner swap fetches balances');
assertEqual(fetchCalls[0], '/api/providers/prov1/balance', 'balance URL is correct');

h.printSummary();
