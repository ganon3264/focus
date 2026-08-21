// Tests for apply* selection entry points.
//
// Selection changes persist through StateManager, then reload every
// selection-dependent pane in one server-rendered OOB response
// (/partials/selection-state). Message-list reloads only for persona and
// character changes, where macro resolution changes message display.

var h = require('./helpers.js');
var assert = h.assert;
var assertEqual = h.assertEqual;
var assertIncludes = h.assertIncludes;

// ── mocks ──
var storage = {};
global.localStorage = {
  getItem: function (k) { return storage.hasOwnProperty(k) ? storage[k] : null; },
  setItem: function (k, v) { storage[k] = String(v); },
  removeItem: function (k) { delete storage[k]; },
};

global._lastFetch = null;
global.fetch = function (url, opts) {
  global._lastFetch = { url: url, opts: opts };
  return Promise.resolve({ ok: true });
};
global.CustomEvent = function (name, opts) {
  this.type = name;
  this.detail = opts ? opts.detail : undefined;
};
global._dispatchedEvents = [];
global.window = global;
global.window.dispatchEvent = function (ev) { global._dispatchedEvents.push(ev); };
global.showInfoToast = function () {};

function el(id) {
  return {
    id: id,
    innerHTML: '',
    textContent: '',
    title: '',
    dataset: {},
    querySelector: function () { return null; },
    querySelectorAll: function () { return []; },
    classList: {
      _set: [],
      add: function (c) { if (this._set.indexOf(c) === -1) this._set.push(c); },
      remove: function (c) {
        var i = this._set.indexOf(c);
        if (i >= 0) this._set.splice(i, 1);
      },
      contains: function (c) { return this._set.indexOf(c) !== -1; },
    },
  };
}

var els = {
  'preset-selector-wrapper': el('preset-selector-wrapper'),
  'preset-selector': el('preset-selector'),
  'preset-variables': el('preset-variables'),
  'arranger-modal-body': el('arranger-modal-body'),
  'preset-add-var-btn': el('preset-add-var-btn'),
  'chat-list': el('chat-list'),
  'message-list': el('message-list'),
  'status-character': el('status-character'),
  'status-persona': el('status-persona'),
  'char-modal-grid': el('char-modal-grid'),
  'persona-modal-grid': el('persona-modal-grid'),
};

global.document = {
  getElementById: function (id) {
    return els[id] || null;
  },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
};

global.Alpine = {
  $data: function () { return null; },
  nextTick: function (cb) { cb(); },
};

var calls = [];
var resolvers = [];
global.htmx = {
  ajax: function (method, url, opts) {
    calls.push({ method: method, url: url, opts: opts });
    return new Promise(function (resolve) { resolvers.push(resolve); });
  },
};

// ── load modules under test ──
var fs = require('fs');
var path = require('path');
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'state-manager.js'), 'utf8'));
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'hx-queue.js'), 'utf8'));
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'selection.js'), 'utf8'));

function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

function resetRequests() {
  calls.length = 0;
  resolvers.length = 0;
}

async function presetScenario() {
  resetRequests();
  StateManager.init({ character_id: 'c1', persona_id: 'p1', preset_id: null }, 'chat-1');

  window.applyPreset('pr1');
  await flush();
  assertEqual(calls.length, 1, 'preset change reloads selection-state');
  assertIncludes(calls[0].url, '/partials/selection-state?chat_id=chat-1', 'selection-state URL');
  assertEqual(calls[0].opts.swap, 'none', 'selection-state swaps via OOB (main swap none)');

  resolvers.shift()();
  await flush();
  assertEqual(calls.length, 1, 'no extra reloads after selection-state settles');

  resetRequests();
  window.applyPreset(null);
  await flush();
  assertEqual(calls.length, 1, 'deselecting preset reloads selection-state too');
  assertIncludes(calls[0].url, '/partials/selection-state?chat_id=chat-1', 'deselect URL');

  resolvers.shift()();
  await flush();
}

async function personaScenario() {
  resetRequests();
  StateManager.init({ character_id: 'c1', persona_id: null, preset_id: 'pr1' }, 'chat-1');

  window.applyPersona('p9', 'Persona Nine');
  await flush();
  assertEqual(calls.length, 1, 'persona change reloads selection-state first');
  assertIncludes(calls[0].url, '/partials/selection-state?chat_id=chat-1', 'selection-state URL');

  resolvers.shift()();
  await flush();
  assertEqual(calls.length, 2, 'message-list reloads after selection-state resolves');
  assertIncludes(calls[1].url, '/partials/message-list/chat-1', 'message-list URL');

  resolvers.shift()();
  await flush();
  assertEqual(StateManager.get('persona_id'), 'p9', 'applyPersona updates StateManager');
  assertEqual(els['status-persona'].textContent, 'Persona Nine', 'applyPersona updates status');
}

async function characterScenario() {
  resetRequests();
  StateManager.init({ character_id: null, persona_id: null, preset_id: 'pr1' }, 'chat-1');

  window.applyCharacter('c9', 'Char Nine');
  await flush();
  assertEqual(calls.length, 1, 'character change reloads selection-state first');
  assertIncludes(calls[0].url, '/partials/selection-state?chat_id=chat-1', 'selection-state URL');

  resolvers.shift()();
  await flush();
  assertEqual(calls.length, 2, 'message-list reloads after selection-state resolves');
  assertIncludes(calls[1].url, '/partials/message-list/chat-1', 'message-list URL');

  resolvers.shift()();
  await flush();
  assertEqual(StateManager.get('character_id'), 'c9', 'applyCharacter updates StateManager');
  assertEqual(els['status-character'].textContent, 'Char Nine', 'applyCharacter updates status');
}

function providerScenario() {
  resetRequests();
  StateManager.init({ provider_id: null, provider_type: null }, 'chat-1');
  var before = global._dispatchedEvents.length;

  window.applyProvider('prov1', 'openai_compat', 'Provider One');

  assertEqual(StateManager.get('provider_id'), 'prov1', 'applyProvider sets provider_id');
  assertEqual(StateManager.get('provider_type'), 'openai_compat', 'applyProvider sets provider_type');
  assert(global._dispatchedEvents.length > before, 'applyProvider emits provider-changed');
  assertEqual(calls.length, 0, 'applyProvider issues no htmx reloads');
}

function syncCardHighlightScenario() {
  var removed = [];
  var added = [];
  var target = el('char-card-c9');
  target.classList.add = function () { added.push('target'); };
  var oldActive = el('char-card-old');
  oldActive.classList.remove = function () { removed.push('old'); };
  var grid = el('char-modal-grid');
  grid.querySelectorAll = function (sel) {
    return sel === '.card.active' ? [oldActive] : [];
  };

  els['char-modal-grid'] = grid;
  els['char-card-c9'] = target;

  StateManager.init({ character_id: 'c9' }, 'chat-1');
  window.syncCardHighlight({ gridId: 'char-modal-grid', stateKey: 'character_id', cardPrefix: 'char-card-' });

  assertIncludes(removed.join(','), 'old', 'syncCardHighlight removes previous active card');
  assertIncludes(added.join(','), 'target', 'syncCardHighlight adds current card');
}

async function main() {
  await presetScenario();
  await personaScenario();
  await characterScenario();
  providerScenario();
  syncCardHighlightScenario();
  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
