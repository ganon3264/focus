// Unit tests for status-panel.js — status bar, cache timer, newChat
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

// Build DOM
function statusSpan(id) {
  var el = makeElement('span');
  el.id = id;
  el.style = {};
  el.title = '';
  return el;
}
var statusProvider = statusSpan('status-provider');
var statusPreset = statusSpan('status-preset');
var statusModel = statusSpan('status-model');
var cacheRow = makeElement('div');
cacheRow.id = 'status-cache-row';
var cacheEl = makeElement('span');
cacheEl.id = 'status-cache';
cacheEl.style = {};

var keyRow = makeElement('div');
keyRow.id = 'status-key-row';
var keyCount = makeElement('span');
keyCount.id = 'status-key-count';
var keyPrev = makeElement('button');
keyPrev.id = 'status-key-prev';
var keyNext = makeElement('button');
keyNext.id = 'status-key-next';

var doc = h.createMockDocument();
doc._body.appendChild(statusProvider);
doc._body.appendChild(statusPreset);
doc._body.appendChild(statusModel);
doc._body.appendChild(cacheRow);
doc._body.appendChild(cacheEl);
doc._body.appendChild(keyRow);
doc._body.appendChild(keyCount);
doc._body.appendChild(keyPrev);
doc._body.appendChild(keyNext);

function mockGetElementById(id) {
  if (id === 'status-provider') return statusProvider;
  if (id === 'status-preset') return statusPreset;
  if (id === 'status-model') return statusModel;
  if (id === 'status-cache-row') return cacheRow;
  if (id === 'status-cache') return cacheEl;
  if (id === 'status-key-row') return keyRow;
  if (id === 'status-key-count') return keyCount;
  if (id === 'status-key-prev') return keyPrev;
  if (id === 'status-key-next') return keyNext;
  return null;
}
doc.getElementById = mockGetElementById;
doc.body = doc._body;
doc.body = doc._body;
doc._body.addEventListener = function () {};
doc.body.addEventListener = function () {};

global.window = global;
global.addEventListener = function () {};
global.document = doc;
global.alert = function () {};
global.fetch = function () { return Promise.resolve({ ok: true }); };
global.setInterval = function () { return 1; };
global.setTimeout = function (fn) { if (typeof fn === 'function') fn(); };
global.htmx = { ajax: function () {} };
global.api = {
  chats: '/api/chats',
  partials: { promptArranger: function (id) { return '/partials/prompt-arranger/' + id; } },
  providerActiveKey: function (id) { return '/api/providers/' + id + '/active-key'; },
};
global.StateManager = {
  get: function (key) {
    if (key === 'provider_id') return 'prov1';
    return null;
  },
  getAll: function () { return { character_id: null, persona_id: null, preset_id: null }; },
};
global.APP_PROVIDERS = [
  { id: 'prov1', name: 'My Provider', type: 'openai_compat', model: 'gpt-4' },
];

// Load module — export bare functions
var src = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'status-panel.js'), 'utf8');
eval(src + '\nwindow.updateStatusPanel=updateStatusPanel;window.updateCacheTimer=updateCacheTimer;window.newChat=newChat;window.updateKeySwitcher=updateKeySwitcher;window._providerKeys=_providerKeys;');

// ── updateStatusPanel shows provider info ──
(function () {
  window.updateStatusPanel();
  assertEqual(statusProvider.textContent, 'openai_compat', 'provider type displayed');
  assertEqual(statusPreset.textContent, 'My Provider', 'provider name displayed');
  assertEqual(statusModel.textContent, 'gpt-4', 'model displayed');
})();

// ── updateStatusPanel shows None when no active provider ──
(function () {
  var oldGet = global.StateManager.get;
  global.StateManager.get = function () { return null; };
  window.updateStatusPanel();
  assertEqual(statusProvider.textContent, 'None', 'no provider: shows None');
  global.StateManager.get = oldGet;
})();

// ── updateCacheTimer hides cache row for non-Claude providers ──
(function () {
  cacheRow.classList.remove('hidden');
  window.updateCacheTimer();
  assert(cacheRow.classList.contains('hidden'), 'cache row hidden for non-Claude');
})();

// ── updateCacheTimer shows cache for Claude providers ──
(function () {
  global.isClaudeProvider = function (p) { return p && p.id === 'prov2'; };
  global.StateManager.get = function () { return 'prov2'; };
  global.APP_PROVIDERS = [{ id: 'prov2', name: 'Claude', type: 'anthropic' }];
  global.getClaudeCacheTimer = function () { return 125000; };

  cacheRow.classList.add('hidden');
  window.updateCacheTimer();
  assert(!cacheRow.classList.contains('hidden'), 'cache row visible for Claude');
  assertEqual(cacheEl.textContent, '2m 05s', 'cache timer formatted as 2m 05s');
})();

// ── updateCacheTimer shows — when no timer ──
(function () {
  global.getClaudeCacheTimer = function () { return null; };
  window.updateCacheTimer();
  assertEqual(cacheEl.textContent, '—', 'cache shows em-dash when no timer');
})();

// ── newChat POSTs and navigates ──
(function () {
  var postUrl = null;
  var oldFetch = global.fetch;
  global.fetch = function (url, opts) {
    postUrl = url;
    return Promise.resolve({ ok: true, json: function () { return { id: 'new-chat-id' }; } });
  };

  global.window.location = { href: '' };

  window.newChat();
  // fetch is async — flush microtasks
  Promise.resolve().then(function () {
    assertEqual(postUrl, '/api/chats', 'newChat POSTs to /api/chats');
    global.fetch = oldFetch;
  });
})();

// ── updateStatusPanel with fallback DOM scraping ──
(function () {
  var oldGet = global.StateManager.get;
  global.StateManager.get = function () { return 'prov-unknown'; };
  global.APP_PROVIDERS = [];

  var cardDisplay = makeElement('div');
  cardDisplay.id = 'prov-display-prov-unknown';
  var strong = makeElement('strong');
  strong.textContent = 'Fallback Provider';
  var textMuted = makeElement('div');
  textMuted.classList.add('text-muted');
  textMuted.textContent = 'google_vertex • gemini-pro';
  cardDisplay.appendChild(strong);
  cardDisplay.appendChild(textMuted);
  doc._body.appendChild(cardDisplay);
  doc.getElementById = function (id) {
    if (id === 'prov-display-prov-unknown') return cardDisplay;
    return mockGetElementById(id);
  };

  window.updateStatusPanel();
  assertEqual(statusProvider.textContent, 'google_vertex', 'fallback: type from DOM');
  assertEqual(statusModel.textContent, 'gemini-pro', 'fallback: model from DOM');
  doc.getElementById = mockGetElementById;
  global.StateManager.get = oldGet;
})();

// ── updateStatusPanel shows Unknown when no provider found ──
(function () {
  var oldGet = global.StateManager.get;
  global.StateManager.get = function () { return 'prov-missing'; };
  global.APP_PROVIDERS = [];

  window.updateStatusPanel();
  assertEqual(statusProvider.textContent, 'Unknown', 'missing provider: shows Unknown');
  global.StateManager.get = oldGet;
})();

// ── Key switcher: multi-key reveals controls and reflects position ──
(function () {
  var oldGet = global.StateManager.get;
  global.StateManager.get = function () { return 'prov1'; };
  global.APP_PROVIDERS = [{
    id: 'prov1', name: 'P', type: 'openai_compat', model: 'm',
    params_json: JSON.stringify({ api_keys: ['SECRET:a', 'SECRET:b', 'SECRET:c'], active_key: 'SECRET:b' }),
  }];
  window.updateStatusPanel();
  assert(!keyRow.classList.contains('hidden'), 'multi-key row visible');
  assertEqual(keyCount.textContent, '2/3', 'key count reflects active position');

  global.APP_PROVIDERS[0].params_json = JSON.stringify({ api_keys: ['SECRET:a', 'SECRET:b'], active_key: 'SECRET:b' });
  window.updateKeySwitcher(global.APP_PROVIDERS[0]);
  assertEqual(keyCount.textContent, '2/2', 'key count follows the active ref');
  global.StateManager.get = oldGet;
})();

// ── Key switcher: single key hides controls ──
(function () {
  global.APP_PROVIDERS = [{ id: 'prov1', name: 'P', type: 't', model: 'm', api_key: 'sk-only' }];
  window.updateKeySwitcher(global.APP_PROVIDERS[0]);
  assert(keyRow.classList.contains('hidden'), 'single-key row hidden');
})();

// ── Key switcher: action POSTs the chosen key and wraps ──
(function () {
  var oldGet = global.StateManager.get;
  global.StateManager.get = function () { return 'prov1'; };
  global.APP_PROVIDERS = [{
    id: 'prov1', name: 'P', type: 'openai_compat', model: 'm',
    params_json: JSON.stringify({ api_keys: ['SECRET:a', 'SECRET:b'], active_key: 'SECRET:a' }),
  }];
  var url = null, bodies = [];
  var oldFetch = global.fetch;
  global.fetch = function (u, opts) { url = u; bodies.push(opts && opts.body); return Promise.resolve({ ok: true }); };
  var el = makeElement('button');

  el.dataset.dir = '1';
  window.actionShiftProviderKey(el);
  assertEqual(url, '/api/providers/prov1/active-key', 'switch POSTs to the active-key endpoint');
  assertEqual(bodies[0], JSON.stringify({ key: 'SECRET:b' }), 'next from the first key advances');
  assert(el.disabled !== true, 'arrow stays clickable after a switch');

  el.dataset.dir = '-1';
  window.actionShiftProviderKey(el);
  assertEqual(bodies[1], JSON.stringify({ key: 'SECRET:b' }), 'previous from the first key wraps to the last');

  global.fetch = oldFetch;
  global.StateManager.get = oldGet;
})();

// ── Result ──
h.printSummary();
