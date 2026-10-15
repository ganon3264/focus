// Unit tests for core/character-store.js — the client SSOT for character records.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;

var path = require('path');
var fs = require('fs');

var env = h.setupBrowserGlobals(global);
global.api = { charactersList: '/api/characters' };

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'character-store.js'), 'utf8'));

function eventsOf(type) {
  return env._dispatchedEvents.filter(function (e) { return e.type === type; });
}

async function main() {
  // ── init / all / get ──
  CharacterStore.init([{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }]);
  assertEqual(CharacterStore.all().length, 2, 'init seeds the list');
  assertEqual(CharacterStore.get('a').name, 'A', 'get returns the matching record');
  assertEqual(CharacterStore.get('nope'), null, 'get returns null for a miss');
  assertEqual(CharacterStore.get(null), null, 'get(null) is null');

  // ── upsert adds then replaces, emitting one change each time ──
  var seen = [];
  CharacterStore.on(function (d) { seen.push(d); });
  CharacterStore.upsert({ id: 'c', name: 'C' });
  assertEqual(CharacterStore.all().length, 3, 'upsert appends a new record');
  CharacterStore.upsert({ id: 'a', name: 'A2' });
  assertEqual(CharacterStore.all().length, 3, 'upsert replaces instead of duplicating');
  assertEqual(CharacterStore.get('a').name, 'A2', 'upsert replaces in place');
  assertEqual(seen.length, 2, 'subscriber notified per upsert');
  assertEqual(eventsOf('characters-changed').length, 2, 'window event per upsert');
  CharacterStore.off(function () {});

  // ── remove ──
  CharacterStore.remove('b');
  assertEqual(CharacterStore.all().length, 2, 'remove drops the record');
  assertEqual(CharacterStore.get('b'), null, 'removed record is gone');
  var eventsBefore = eventsOf('characters-changed').length;
  CharacterStore.remove('missing');
  assertEqual(eventsOf('characters-changed').length, eventsBefore, 'removing a miss does not emit');

  // ── refresh pulls the authoritative list ──
  global.fetch = function (url) {
    assertEqual(url, '/api/characters', 'refresh hits the characters endpoint');
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve([{ id: 'z', name: 'Z' }]); } });
  };
  await CharacterStore.refresh();
  assertDeepEqual(CharacterStore.all(), [{ id: 'z', name: 'Z' }], 'refresh replaces the list');

  // ── failed refresh leaves the previous list intact ──
  global.fetch = function () { return Promise.resolve({ ok: false }); };
  await CharacterStore.refresh();
  assertEqual(CharacterStore.all().length, 1, 'failed refresh keeps the current list');

  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
