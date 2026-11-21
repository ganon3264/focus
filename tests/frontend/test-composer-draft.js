// The composer draft is one localStorage snapshot per chat, debounced while
// typing. These tests pin the two things that made it lose text: the pending
// debounce dying with the page, and the timer resolving the chat id late.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var path = require('path');
var fs = require('fs');

function makeTextarea() {
  var listeners = {};
  return {
    id: 'chat-input',
    value: '',
    placeholder: 'Type a message…',
    style: {},
    scrollHeight: 20,
    addEventListener: function (name, fn) { (listeners[name] = listeners[name] || []).push(fn); },
    dispatch: function (name, ev) {
      var self = this;
      (listeners[name] || []).forEach(function (fn) { fn.call(self, ev || {}); });
    },
  };
}

var input = makeTextarea();
var sendBtn = {
  dataset: {},
  innerHTML: '',
  title: '',
  classList: { contains: function () { return false; }, add: function () {}, remove: function () {} },
};

var docListeners = {};
var winListeners = {};
var chatId = 'chat1';

global.window = global;
global.localStorage = h.createMockLocalStorage();
global.document = {
  body: { addEventListener: function () {} },
  visibilityState: 'visible',
  getElementById: function (id) {
    if (id === 'chat-input') return input;
    if (id === 'send-btn') return sendBtn;
    return null;
  },
  addEventListener: function (name, fn) { (docListeners[name] = docListeners[name] || []).push(fn); },
};
global.addEventListener = function (name, fn) { (winListeners[name] = winListeners[name] || []).push(fn); };
global.getComputedStyle = function () { return { maxHeight: '248px' }; };
global.getSvgSprite = function () { return ''; };
global.StateManager = { get: function (key) { return key === 'chat_id' ? chatId : null; } };
global.Prefs = { get: function () { return 'enter'; } };

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'input-bar.js'), 'utf8'));

function fireDoc(name) { (docListeners[name] || []).forEach(function (fn) { fn(); }); }
function fireWin(name) { (winListeners[name] || []).forEach(function (fn) { fn(); }); }
function wait(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

(async function () {
  // ── Typing is debounced, and the whole value is one snapshot ──
  input.value = 'line one\nline two\nline three';
  input.dispatch('input');
  assertEqual(localStorage.getItem('focus-draft-chat1'), null, 'draft: write is held back while typing');

  await wait(320);
  assertEqual(
    localStorage.getItem('focus-draft-chat1'),
    'line one\nline two\nline three',
    'draft: multi-line value stored intact',
  );

  // ── Newlines survive the round trip ──
  input.value = '';
  fireDoc('DOMContentLoaded');
  assertEqual(input.value, 'line one\nline two\nline three', 'draft: restored with newlines');
  assertEqual(input.style.height, '20px', 'draft: restored text is measured');

  // ── The draft is newer than the browser's kept form state ──
  input.value = 'what the browser restored';
  fireDoc('DOMContentLoaded');
  assertEqual(input.value, 'line one\nline two\nline three', 'draft: saved draft wins over restored form state');

  // ── Firefox fills the field after DOMContentLoaded, with no input event ──
  input.value = '';
  input.style.height = '';
  input.value = 'restored by the browser\nafter our hook';
  fireWin('load');
  assertEqual(input.style.height, '20px', 'draft: page load re-measures a field the browser filled');
  input.style.height = '';
  fireWin('pageshow');
  assertEqual(input.style.height, '20px', 'draft: bfcache return re-measures');

  // ── Leaving the page flushes what the debounce still holds ──
  localStorage.removeItem('focus-draft-chat1');
  input.value = 'typed and reloaded immediately';
  input.dispatch('input');
  fireWin('pagehide');
  assertEqual(
    localStorage.getItem('focus-draft-chat1'),
    'typed and reloaded immediately',
    'draft: pagehide flushes the pending write',
  );

  // ── Backgrounding the tab flushes too (mobile close path) ──
  localStorage.removeItem('focus-draft-chat1');
  input.value = 'app backgrounded';
  input.dispatch('input');
  global.document.visibilityState = 'hidden';
  fireDoc('visibilitychange');
  global.document.visibilityState = 'visible';
  assertEqual(localStorage.getItem('focus-draft-chat1'), 'app backgrounded', 'draft: hidden tab flushes');

  // ── A chat switch inside the debounce window stays with its own chat ──
  localStorage.removeItem('focus-draft-chat1');
  localStorage.removeItem('focus-draft-chat2');
  input.value = 'written in chat one';
  input.dispatch('input');
  chatId = 'chat2';
  await wait(320);
  assertEqual(
    localStorage.getItem('focus-draft-chat1'),
    'written in chat one',
    'draft: late timer writes under the chat it was typed in',
  );
  assertEqual(localStorage.getItem('focus-draft-chat2'), null, 'draft: the next chat is untouched');

  // ── Clearing on send cancels whatever was pending ──
  input.value = 'sent already';
  input.dispatch('input');
  window.clearComposerDraft();
  input.value = '';
  await wait(320);
  assertEqual(localStorage.getItem('focus-draft-chat2'), null, 'draft: send clears and cancels');

  h.printSummary();
})();
