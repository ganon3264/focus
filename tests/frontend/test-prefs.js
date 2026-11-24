// Unit tests for Prefs (static/js/core/prefs.js)
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;

var props = {};
var events = [];
var calls = [];
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
  calls.push({ url: url, method: method, body: body });
  return Promise.resolve({
    ok: nextResponse.ok,
    json: function () { return Promise.resolve(nextResponse.body); },
  });
};

var fs = require('fs'), path = require('path');
window.PREFS = {
  send_key: 'enter',
  follow_stream: 'pinned',
  reasoning_open: 'off',
  clock: '12h',
  chat_width: 900,
  text_size: 'medium',
  prune_messages: false,
};
window.api = { settingsPrefs: '/api/settings/prefs' };
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'prefs.js'), 'utf8'));

function lastCall() { return calls[calls.length - 1]; }

async function main() {
  // ── the server-rendered blob is in force before the first paint.
  assertEqual(props['--chat-content-width'], 'min(100%, 900px)', 'width applied at load');
  assertEqual(document.documentElement.dataset.clock, '12h', 'clock applied at load');
  assertEqual(document.documentElement.dataset.textSize, 'medium', 'text size applied at load');
  assertEqual(Prefs.get('prune_messages'), false, 'server value wins over nothing');

  // ── a set applies immediately, announces, and PUTs the patch.
  events.length = 0;
  await Prefs.set({ clock: '24h' });
  assertEqual(document.documentElement.dataset.clock, '24h', 'clock change applied');
  assertEqual(props['--chat-content-width'], 'min(100%, 900px)', 'unrelated change keeps the width');
  assertEqual(events.length, 1, 'one event for one key');
  assertEqual(events[0].type, 'prefs-changed', 'event name');
  assertEqual(events[0].detail.key, 'clock', 'event names the key');
  assertEqual(lastCall().url, '/api/settings/prefs', 'PUTs the prefs endpoint');
  assertEqual(lastCall().method, 'PUT', 'uses PUT');

  // ── the server's normalized answer replaces the optimistic state.
  nextResponse = { ok: true, body: { send_key: 'ctrl_enter', follow_stream: 'pinned', reasoning_open: 'stream', clock: '24h', chat_width: 640, text_size: 'medium', prune_messages: true } };
  await Prefs.set({ send_key: 'ctrl_enter' });
  assertEqual(Prefs.get('send_key'), 'ctrl_enter', 'saved send_key kept');
  assertEqual(Prefs.get('chat_width'), 640, 'server answer wins');
  assertEqual(props['--chat-content-width'], 'min(100%, 640px)', 'width re-applied from the answer');

  // ── reset drops the blob and takes the server's defaults, with no key list.
  nextResponse = { ok: true, body: { send_key: 'enter', follow_stream: 'pinned', reasoning_open: 'off', clock: '24h', chat_width: 800, text_size: 'medium', prune_messages: true } };
  events.length = 0;
  await Prefs.reset();
  assertEqual(lastCall().method, 'DELETE', 'reset DELETEs the blob');
  assertEqual(lastCall().url, '/api/settings/prefs', 'reset targets the prefs endpoint');
  assertDeepEqual(Prefs.all(), nextResponse.body, 'reset adopts the server defaults');
  assertEqual(props['--chat-content-width'], 'min(100%, 800px)', 'reset restores the width');
  assertEqual(document.documentElement.dataset.clock, '24h', 'reset restores the clock');
  assertDeepEqual(
    events.map(function (e) { return e.detail.key; }).sort(),
    Object.keys(nextResponse.body).sort(),
    'reset announces every key it replaced',
  );

  // ── a failed save rolls the optimistic state back and re-announces it.
  nextResponse = { ok: false, body: null };
  events.length = 0;
  await Prefs.set({ chat_width: 1600 });
  assertEqual(Prefs.get('chat_width'), 800, 'failed save restores the previous value');
  assertEqual(props['--chat-content-width'], 'min(100%, 800px)', 'failed save restores the width');
  assertEqual(events[events.length - 1].detail.value, 800, 'rollback is announced');

  // ── a failed reset keeps the current state.
  nextResponse = { ok: false, body: null };
  await Prefs.reset();
  assertEqual(Prefs.get('chat_width'), 800, 'failed reset keeps the state');

  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
