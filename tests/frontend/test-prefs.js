// Unit tests for Prefs (static/js/core/prefs.js)
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;

var props = {};
var events = [];
var puts = [];
var nextResponse = { ok: true, body: null };

global.window = global;
global.CustomEvent = function (name, opts) {
  this.type = name;
  this.detail = opts ? opts.detail : undefined;
};
window.dispatchEvent = function (ev) { events.push(ev); };
global.document = {
  documentElement: {
    style: { setProperty: function (k, v) { props[k] = v; } },
    dataset: {},
  },
};
global.hxJson = function (url, method, body) {
  puts.push({ url: url, method: method, body: body });
  return Promise.resolve({
    ok: nextResponse.ok,
    json: function () { return Promise.resolve(nextResponse.body); },
  });
};

var fs = require('fs'), path = require('path');
window.PREFS = { clock: '12h', chat_width: 900, prune_messages: false };
window.api = { settingsPrefs: '/api/settings/prefs' };
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'prefs.js'), 'utf8'));

async function main() {
  // ── the server-rendered blob is in force before the first paint.
  assertEqual(props['--chat-content-width'], 'min(100%, 900px)', 'width applied at load');
  assertEqual(document.documentElement.dataset.clock, '12h', 'clock applied at load');
  assertEqual(Prefs.get('send_key'), 'enter', 'missing key falls back to its default');
  assertEqual(Prefs.get('prune_messages'), false, 'server value wins over the default');

  // ── a set applies immediately, announces, and persists the whole patch.
  events.length = 0;
  await Prefs.set({ clock: '24h', bogus: 1 });
  assertEqual(props['--chat-content-width'], 'min(100%, 900px)', 'unrelated change keeps the width');
  assertEqual(document.documentElement.dataset.clock, '24h', 'clock change applied');
  assertEqual(events.length, 1, 'one event for one known key, unknown key ignored');
  assertEqual(events[0].type, 'prefs-changed', 'event name');
  assertEqual(events[0].detail.key, 'clock', 'event names the key');
  assertEqual(puts.length, 1, 'one PUT for the patch');
  assertEqual(puts[0].url, '/api/settings/prefs', 'PUTs the prefs endpoint');
  assertEqual(puts[0].method, 'PUT', 'uses PUT');

  // ── the server's normalized answer replaces the optimistic state.
  nextResponse = { ok: true, body: { send_key: 'ctrl_enter', clock: '24h', chat_width: 640, prune_messages: true } };
  await Prefs.set({ send_key: 'ctrl_enter' });
  assertEqual(Prefs.get('send_key'), 'ctrl_enter', 'saved send_key kept');
  assertEqual(Prefs.get('chat_width'), 640, 'server answer wins');
  assertEqual(props['--chat-content-width'], 'min(100%, 640px)', 'width re-applied from the answer');

  // ── a failed save rolls the optimistic state back and re-announces it.
  nextResponse = { ok: false, body: null };
  events.length = 0;
  await Prefs.set({ chat_width: 1600 });
  assertEqual(Prefs.get('chat_width'), 640, 'failed save restores the previous value');
  assertEqual(props['--chat-content-width'], 'min(100%, 640px)', 'failed save restores the width');
  assertEqual(events[events.length - 1].detail.value, 640, 'rollback is announced');

  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
