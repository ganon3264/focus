// tests/test_state_manager.js — unit tests for StateManager
// Run: node tests/test_state_manager.js

var failures = 0;
var tests = 0;

function assert(condition, msg) {
  tests++;
  if (!condition) { console.error('FAIL: ' + msg); failures++; }
  else { console.log('OK:   ' + msg); }
}

function assertEqual(actual, expected, msg) {
  tests++;
  if (actual !== expected) {
    console.error('FAIL: ' + msg + ' — expected ' + JSON.stringify(expected) + ', got ' + JSON.stringify(actual));
    failures++;
  } else { console.log('OK:   ' + msg); }
}

function assertDeepEqual(actual, expected, msg) {
  var a = JSON.stringify(actual), b = JSON.stringify(expected);
  tests++;
  if (a !== b) {
    console.error('FAIL: ' + msg + ' — expected ' + b + ', got ' + a);
    failures++;
  } else { console.log('OK:   ' + msg); }
}

// Browser API mocks
var storage = {};
global.localStorage = {
  getItem: function(k) { return storage.hasOwnProperty(k) ? storage[k] : null; },
  setItem: function(k, v) { storage[k] = String(v); },
  removeItem: function(k) { delete storage[k]; }
};
global._lastFetch = null;
global.fetch = function(url, opts) {
  global._lastFetch = { url: url, opts: opts };
  return Promise.resolve({ ok: true });
};
global.CustomEvent = function(name, opts) {
  this.type = name; this.detail = opts ? opts.detail : undefined;
};
global._dispatchedEvents = [];
global.window = global;
global.window.dispatchEvent = function(ev) { global._dispatchedEvents.push(ev); };

// Load StateManager
var fs = require('fs'), path = require('path');
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'state_manager.js'), 'utf8'));

function reset() {
  storage = {};
  global._lastFetch = null;
  global._dispatchedEvents = [];
}

// ── init() ──
(function() {
  reset();
  StateManager.init({ character_id: 'c1', persona_id: 'p1', preset_id: 'pr1' }, 'chat1');
  assertEqual(StateManager.get('character_id'), 'c1', 'init sets character_id');
  assertEqual(StateManager.get('persona_id'), 'p1', 'init sets persona_id');
  assertEqual(StateManager.get('preset_id'), 'pr1', 'init sets preset_id');
  assertEqual(StateManager.get('provider_id'), null, 'init provider_id null when localStorage empty');
  assertEqual(StateManager.get('provider_type'), null, 'init provider_type null when localStorage empty');
})();

// ── init() reads provider from localStorage ──
(function() {
  reset();
  localStorage.setItem('focus-provider-id', 'prov1');
  localStorage.setItem('focus-provider-type', 'openai_compat');
  StateManager.init({ character_id: null, persona_id: null, preset_id: null }, 'chat1');
  assertEqual(StateManager.get('provider_id'), 'prov1', 'init reads provider_id from localStorage');
  assertEqual(StateManager.get('provider_type'), 'openai_compat', 'init reads provider_type from localStorage');
})();

// ── setPreset() + callback ──
(function() {
  reset();
  StateManager.init({ character_id: null, persona_id: null, preset_id: null }, 'chat2');
  var events = [];
  StateManager.on('preset-changed', function(e) { events.push(e); });

  StateManager.setPreset('pr2');
  assertEqual(StateManager.get('preset_id'), 'pr2', 'setPreset updates state');
  assertEqual(events.length, 1, 'setPreset fires callback');
  assertEqual(events[0].prev, null, 'prev is null on first set');
  assertEqual(events[0].value, 'pr2', 'value is new id');
  assert(global._lastFetch.url.indexOf('/api/chats/chat2') >= 0, 'fetch URL has chatId');
  assertEqual(global._lastFetch.opts.method, 'PATCH', 'fetch method is PATCH');
  assertEqual(JSON.parse(global._lastFetch.opts.body).preset_id, 'pr2', 'fetch body has preset_id');

  StateManager.setPreset('pr3');
  assertEqual(events.length, 2, 'second setPreset fires callback');
  assertEqual(events[1].prev, 'pr2', 'second prev is old id');
  assertEqual(events[1].value, 'pr3', 'second value is new id');
})();

// ── setPreset(null) ──
(function() {
  reset();
  StateManager.init({ character_id: null, persona_id: null, preset_id: 'pr2' }, 'chat3');
  var events = [];
  StateManager.on('preset-changed', function(e) { events.push(e); });

  StateManager.setPreset(null);
  assertEqual(StateManager.get('preset_id'), null, 'setPreset(null) clears state');
  assertEqual(events.length, 1, 'setPreset(null) fires callback');
  assertEqual(events[0].prev, 'pr2', 'prev is old id');
  assertEqual(events[0].value, null, 'value is null');
  assertEqual(JSON.parse(global._lastFetch.opts.body).preset_id, null, 'fetch body has null');
})();

// ── setCharacter() ──
(function() {
  reset();
  StateManager.init({ character_id: 'c1', persona_id: null, preset_id: null }, 'chat4');
  var events = [];
  StateManager.on('character-changed', function(e) { events.push(e); });

  StateManager.setCharacter('c2');
  assertEqual(StateManager.get('character_id'), 'c2', 'setCharacter updates state');
  assertEqual(events.length, 1, 'setCharacter fires callback');
  assertEqual(events[0].prev, 'c1', 'prev is old id');
  assertEqual(events[0].value, 'c2', 'value is new id');
  assert(global._lastFetch.url.indexOf('/api/chats/chat4') >= 0, 'fetch URL has chatId');
})();

// ── setPersona() ──
(function() {
  reset();
  StateManager.init({ character_id: null, persona_id: null, preset_id: null }, 'chat5');
  var events = [];
  StateManager.on('persona-changed', function(e) { events.push(e); });

  StateManager.setPersona('p2');
  assertEqual(StateManager.get('persona_id'), 'p2', 'setPersona updates state');
  assertEqual(events.length, 1, 'setPersona fires callback');
  assertEqual(events[0].prev, null, 'prev is null');
  assertEqual(events[0].value, 'p2', 'value is new id');
})();

// ── setProvider() + localStorage + window event ──
(function() {
  reset();
  StateManager.init({ character_id: null, persona_id: null, preset_id: null }, null);
  var cb = [];
  StateManager.on('provider-changed', function(e) { cb.push(e); });

  StateManager.setProvider('prov1', 'openai_compat');
  assertEqual(StateManager.get('provider_id'), 'prov1', 'setProvider updates provider_id');
  assertEqual(StateManager.get('provider_type'), 'openai_compat', 'setProvider updates provider_type');
  assertEqual(localStorage.getItem('focus-provider-id'), 'prov1', 'persists id to localStorage');
  assertEqual(localStorage.getItem('focus-provider-type'), 'openai_compat', 'persists type to localStorage');
  assertEqual(cb.length, 1, 'fires callback');
  assertEqual(cb[0].prevId, null, 'prevId is null');
  assertEqual(cb[0].id, 'prov1', 'id is set');
  assertEqual(cb[0].type, 'openai_compat', 'type is set');
  assertEqual(global._dispatchedEvents.length, 1, 'dispatches window CustomEvent');
  assertEqual(global._dispatchedEvents[0].type, 'provider-changed', 'CustomEvent type');
  assertDeepEqual(global._dispatchedEvents[0].detail, { id: 'prov1', type: 'openai_compat' }, 'CustomEvent detail');

  StateManager.setProvider('prov2', 'google_aistudio');
  assertEqual(cb.length, 2, 'second setProvider fires callback');
  assertEqual(cb[1].prevId, 'prov1', 'second prevId');
  assertEqual(cb[1].prevType, 'openai_compat', 'second prevType');
  assertEqual(global._dispatchedEvents.length, 2, 'second CustomEvent');

  StateManager.setProvider(null, null);
  assertEqual(StateManager.get('provider_id'), null, 'setProvider(null, null) clears id');
  assertEqual(localStorage.getItem('focus-provider-id'), null, 'removes localStorage id');
  assertEqual(localStorage.getItem('focus-provider-type'), null, 'removes localStorage type');
})();

// ── setProvider without type → no CustomEvent ──
(function() {
  reset();
  StateManager.init({}, null);
  StateManager.setProvider('provX', null);
  assertEqual(StateManager.get('provider_id'), 'provX', 'provider_id set even without type');
  assertEqual(StateManager.get('provider_type'), null, 'provider_type cleared');
  assertEqual(localStorage.getItem('focus-provider-id'), 'provX', 'id persisted');
  assertEqual(localStorage.getItem('focus-provider-type'), null, 'type not in localStorage');
  assertEqual(global._dispatchedEvents.length, 0, 'no CustomEvent when type is null');
})();

// ── getAll() ──
(function() {
  reset();
  StateManager.init({ character_id: 'ca', persona_id: 'pa', preset_id: 'pra' }, 'chatX');
  assertDeepEqual(StateManager.getAll(), {
    character_id: 'ca', persona_id: 'pa', preset_id: 'pra',
    provider_id: null, provider_type: null
  }, 'getAll returns all 5 fields');
})();

// ── No chatId → no fetch ──
(function() {
  reset();
  StateManager.init({ character_id: null, persona_id: null, preset_id: null }, null);

  StateManager.setPreset('prX');
  assertEqual(StateManager.get('preset_id'), 'prX', 'setPreset updates state without chatId');
  assertEqual(global._lastFetch, null, 'setPreset without chatId does not call fetch');
})();

// ── off() unregisters listener ──
(function() {
  reset();
  StateManager.init({ character_id: null, persona_id: null, preset_id: null }, null);

  var calls = 0;
  function listener() { calls++; }
  StateManager.on('preset-changed', listener);
  StateManager.setPreset('x1');
  assertEqual(calls, 1, 'listener fires');

  StateManager.off('preset-changed', listener);
  StateManager.setPreset('x2');
  assertEqual(calls, 1, 'listener does not fire after off');
})();

// ── setPreset with same value — still fires (StateManager always does) ──
(function() {
  reset();
  StateManager.init({ preset_id: 'same' }, 'chat6');
  var calls = 0;
  StateManager.on('preset-changed', function() { calls++; });
  StateManager.setPreset('same');
  assertEqual(calls, 1, 'setPreset(same) still fires callback');
  assertEqual(StateManager.get('preset_id'), 'same', 'setPreset(same) keeps value');
})();

// ── setCharacter with null clears ──
(function() {
  reset();
  StateManager.init({ character_id: 'c1' }, 'chat7');
  var events = [];
  StateManager.on('character-changed', function(e) { events.push(e); });
  StateManager.setCharacter(null);
  assertEqual(StateManager.get('character_id'), null, 'setCharacter(null) clears');
  assertEqual(events[0].prev, 'c1', 'setCharacter(null) prev is old id');
  assertEqual(events[0].value, null, 'setCharacter(null) value is null');
  assertEqual(JSON.parse(global._lastFetch.opts.body).character_id, null, 'fetch body has null character_id');
})();

// ── setPersona with null clears ──
(function() {
  reset();
  StateManager.init({ persona_id: 'p1' }, 'chat8');
  StateManager.setPersona(null);
  assertEqual(StateManager.get('persona_id'), null, 'setPersona(null) clears');
})();

// ── Multiple callbacks on same event ──
(function() {
  reset();
  StateManager.init({ preset_id: null }, 'chat9');
  var count = 0;
  StateManager.on('preset-changed', function() { count++; });
  StateManager.on('preset-changed', function() { count++; });
  StateManager.setPreset('multi');
  assertEqual(count, 2, 'multiple callbacks both fire');
})();

// ── setCharacter PATCH body shape ──
(function() {
  reset();
  StateManager.init({ character_id: 'old' }, 'chat10');
  StateManager.setCharacter('newChar');
  var body = JSON.parse(global._lastFetch.opts.body);
  assertEqual(body.character_id, 'newChar', 'setCharacter PATCH body has character_id');
  assert(!body.hasOwnProperty('preset_id'), 'setCharacter PATCH body does not include preset_id');
  assert(!body.hasOwnProperty('persona_id'), 'setCharacter PATCH body does not include persona_id');
})();

// ── setPersona PATCH body shape ──
(function() {
  reset();
  StateManager.init({ persona_id: null }, 'chat11');
  StateManager.setPersona('newPersona');
  var body = JSON.parse(global._lastFetch.opts.body);
  assertEqual(body.persona_id, 'newPersona', 'setPersona PATCH body has persona_id');
  assert(!body.hasOwnProperty('character_id'), 'setPersona PATCH body does not include character_id');
})();

// ── get() on unknown key returns undefined ──
(function() {
  reset();
  StateManager.init({}, null);
  assertEqual(StateManager.get('nonexistent'), undefined, 'get(unknown) returns undefined');
})();

// ── init() with null chatId — no fetch on set ──
(function() {
  reset();
  StateManager.init({ character_id: null, persona_id: null, preset_id: null }, null);
  StateManager.setCharacter('c99');
  assertEqual(global._lastFetch, null, 'no chatId: setCharacter does not fetch');
  StateManager.setPersona('p99');
  assertEqual(global._lastFetch, null, 'no chatId: setPersona does not fetch');
})();

// ── Provider: setProvider with previous values ──
(function() {
  reset();
  localStorage.setItem('focus-provider-id', 'oldId');
  localStorage.setItem('focus-provider-type', 'oldType');
  StateManager.init({}, null);
  var events = [];
  StateManager.on('provider-changed', function(e) { events.push(e); });
  StateManager.setProvider('newId', 'newType');
  assertEqual(events[0].prevId, 'oldId', 'provider prevId from localStorage');
  assertEqual(events[0].prevType, 'oldType', 'provider prevType from localStorage');
  assertEqual(localStorage.getItem('focus-provider-id'), 'newId', 'provider persists new id');
  assertEqual(localStorage.getItem('focus-provider-type'), 'newType', 'provider persists new type');
})();

// ── off() on non-registered listener — no crash ──
(function() {
  reset();
  StateManager.init({}, null);
  StateManager.off('preset-changed', function() {});
  assert(true, 'off(non-registered) does not throw');
})();

// ── Result ──
console.log('\n' + tests + ' tests, ' + failures + ' failures');
process.exit(failures > 0 ? 1 : 0);
