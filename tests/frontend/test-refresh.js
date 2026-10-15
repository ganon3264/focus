// Unit tests for core/refresh.js — the central resource -> surface invalidation
// registry: fan-out, cover-collapse, coalescing, streaming guard, `when`,
// explicit load, mutate, and the dev warning.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertIncludes = h.assertIncludes;

var path = require('path');
var fs = require('fs');

h.setupBrowserGlobals(global);

var counters = {};
function resetCounters() {
  counters = { selection: 0, messages: 0, chatList: 0, regex: 0, themes: 0, charCards: 0, personaCards: 0 };
  lastChatId = null;
}
var lastChatId = null;

var openModals = {};
global.StateManager = {
  _s: { chat_id: 'chat-1', preset_id: 'pr1' },
  get: function (k) { return this._s[k] || null; },
};
global.ModalController = { isOpen: function (id) { return !!openModals[id]; } };

global.reloadSelectionState = function () { counters.selection++; return Promise.resolve(); };
global.refreshChatMessages = function (chatId) { counters.messages++; lastChatId = chatId; return Promise.resolve(); };
global._refreshChatList = function () { counters.chatList++; return Promise.resolve(); };
global.reloadRegexScripts = function () { counters.regex++; return Promise.resolve(); };
global.refreshThemes = function () { counters.themes++; return Promise.resolve(); };
global.reloadCharacterCards = function () { counters.charCards++; return Promise.resolve(); };
global.reloadPersonaCards = function () { counters.personaCards++; return Promise.resolve(); };

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'refresh.js'), 'utf8'));

async function main() {
  // ── fan-out + cover-collapse: presets touches selection and messages, and
  // selection already redraws the chat list, so chatList must not run twice.
  resetCounters();
  await Refresh.changed('presets');
  assertEqual(counters.selection, 1, 'presets -> selection');
  assertEqual(counters.messages, 1, 'presets -> messages');
  assertEqual(lastChatId, 'chat-1', 'messages load reads chat_id from StateManager');
  assertEqual(counters.chatList, 0, 'chat list covered by selection');
  assertEqual(counters.regex, 0, 'regexList skipped while advanced modal closed');

  // ── coalescing: two resources in one tick flush once.
  resetCounters();
  Refresh.changed('presets');
  await Refresh.changed('characters');
  assertEqual(counters.selection, 1, 'coalesced: selection loaded once');
  assertEqual(counters.messages, 1, 'coalesced: messages loaded once');

  // ── streaming guard skips only the guarded surface.
  resetCounters();
  global.Generation = { isActive: function () { return true; } };
  await Refresh.changed('presets');
  assertEqual(counters.messages, 0, 'messages skipped while streaming');
  assertEqual(counters.selection, 1, 'unguarded surface still refreshes');
  global.Generation = null;

  // ── `when` gates flush, explicit load ignores it.
  resetCounters();
  openModals = {};
  await Refresh.changed('presets');
  assertEqual(counters.regex, 0, 'when=false surface skipped during flush');
  await Refresh.load('regexList');
  assertEqual(counters.regex, 1, 'explicit Refresh.load ignores when');

  // ── characterCards / personaCards surfaces are gated on their modal.
  resetCounters();
  openModals = {};
  await Refresh.changed('characters');
  assertEqual(counters.charCards, 0, 'characterCards skipped while its modal is closed');
  openModals['modal-characters'] = true;
  await Refresh.changed('characters');
  assertEqual(counters.charCards, 1, 'characters -> characterCards when modal open');
  await Refresh.changed('personas');
  assertEqual(counters.personaCards, 0, 'personaCards skipped while its modal is closed');
  openModals['modal-personas'] = true;
  await Refresh.changed('personas');
  assertEqual(counters.personaCards, 1, 'personas -> personaCards when modal open');
  openModals = {};

  // ── themes surface is driven purely by its resources.
  resetCounters();
  await Refresh.changed('themes');
  assertEqual(counters.themes, 1, 'themes -> refreshThemes');

  // ── mutate runs the request through the queue and invalidates on commit.
  resetCounters();
  var fetched = null;
  global.fetch = function (url, opts) { fetched = { url: url, opts: opts }; return Promise.resolve({ ok: true }); };
  await Refresh.mutate('/api/x', { method: 'POST' }, { changed: ['presets'] });
  assert(fetched && fetched.url === '/api/x', 'mutate issues the request');
  assertEqual(fetched.opts.method, 'POST', 'mutate preserves request options');
  assertEqual(counters.selection, 1, 'mutate invalidates declared resources on success');

  // ── a failed mutation invalidates nothing.
  resetCounters();
  global.fetch = function () { return Promise.resolve({ ok: false }); };
  await Refresh.mutate('/api/x', {}, { changed: ['presets'] });
  assertEqual(counters.selection, 0, 'failed mutate does not invalidate');

  // ── a resource no surface depends on warns once in dev.
  var warned = [];
  var origWarn = console.warn;
  console.warn = function (msg) { warned.push(msg); };
  window.DEBUG = true;
  await Refresh.changed('totally_bogus');
  window.DEBUG = false;
  console.warn = origWarn;
  assertEqual(warned.length, 1, 'one dev warning for an unhandled resource');
  assertIncludes(warned[0], 'totally_bogus', 'warning names the resource');

  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
