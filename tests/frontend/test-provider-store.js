// Unit tests for core/provider-store.js — the client SSOT for provider records.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;

var path = require('path');
var fs = require('fs');

var env = h.setupBrowserGlobals(global);
global.api = { providers: '/api/providers' };

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'provider-store.js'), 'utf8'));

function eventsOf(type) {
  return env._dispatchedEvents.filter(function (e) { return e.type === type; });
}

async function main() {
  // ── init / all / get ──
  ProviderStore.init([{ id: 'a', name: 'A' }, { id: 'b', name: 'B' }]);
  assertEqual(ProviderStore.all().length, 2, 'init seeds the list');
  assertEqual(ProviderStore.get('a').name, 'A', 'get returns the matching record');
  assertEqual(ProviderStore.get('nope'), null, 'get returns null for a miss');
  assertEqual(ProviderStore.get(null), null, 'get(null) is null');

  // ── upsert adds then replaces, emitting one change each time ──
  var seen = [];
  ProviderStore.on(function (d) { seen.push(d); });
  ProviderStore.upsert({ id: 'c', name: 'C' });
  assertEqual(ProviderStore.all().length, 3, 'upsert appends a new record');
  ProviderStore.upsert({ id: 'a', name: 'A2' });
  assertEqual(ProviderStore.all().length, 3, 'upsert replaces instead of duplicating');
  assertEqual(ProviderStore.get('a').name, 'A2', 'upsert replaces in place');
  assertEqual(seen.length, 2, 'subscriber notified per upsert');
  assertEqual(eventsOf('providers-changed').length, 2, 'window event per upsert');
  ProviderStore.off(function () {});

  // ── remove ──
  ProviderStore.remove('b');
  assertEqual(ProviderStore.all().length, 2, 'remove drops the record');
  assertEqual(ProviderStore.get('b'), null, 'removed record is gone');
  var eventsBefore = eventsOf('providers-changed').length;
  ProviderStore.remove('missing');
  assertEqual(eventsOf('providers-changed').length, eventsBefore, 'removing a miss does not emit');

  // ── refresh pulls the authoritative list ──
  global.fetch = function (url) {
    assertEqual(url, '/api/providers', 'refresh hits the providers endpoint');
    return Promise.resolve({ ok: true, json: function () { return Promise.resolve([{ id: 'z', name: 'Z' }]); } });
  };
  await ProviderStore.refresh();
  assertDeepEqual(ProviderStore.all(), [{ id: 'z', name: 'Z' }], 'refresh replaces the list');

  // ── failed refresh leaves the previous list intact ──
  global.fetch = function () { return Promise.resolve({ ok: false }); };
  await ProviderStore.refresh();
  assertEqual(ProviderStore.all().length, 1, 'failed refresh keeps the current list');

  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
