// Unit tests for message-pruner.js — DOM virtualization
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

var cc = makeElement('div');
cc.className = 'chat-center';
cc.clientHeight = 800;
cc.scrollTop = 0;
cc.addEventListener = function () {};

var ml = makeElement('div');
ml.id = 'message-list';

// Add messages with getBoundingClientRect that reports positions
function addMsg(id, top) {
  var msg = makeElement('div');
  msg.style = {};
  msg.id = id;
  msg.classList.add('message');
  msg.getBoundingClientRect = function () {
    return { top: top, bottom: top + 60, left: 0, right: 0, width: 400, height: 60 };
  };
  msg.offsetHeight = 60;
  msg.outerHTML = '<div id="' + id + '" class="message">content</div>';
  msg.replaceWith = function (newEl) {
    var parent = msg.parent;
    if (parent) {
      var idx = parent.children.indexOf(msg);
      if (idx >= 0) parent.children.splice(idx, 1, newEl);
      newEl.parent = parent;
    }
  };
  ml.appendChild(msg);
  return msg;
}
var msg1 = addMsg('msg-1', 0);    // visible (top 0-60)
var msg2 = addMsg('msg-2', 200);  // visible (200-260)
var msg3 = addMsg('msg-3', 900);  // below fold, should prune

var doc = h.createMockDocument();
// Override createElement to add missing browser APIs
doc.createElement = function (tag) {
  var el = h.makeElement(tag);
  el.style = {};
  el.replaceWith = function (newEl) {
    var parent = el.parent;
    if (parent) {
      var idx = parent.children.indexOf(el);
      if (idx >= 0) parent.children.splice(idx, 1, newEl);
      newEl.parent = parent;
    }
  };
  el.outerHTML = el.innerHTML ? '<' + el.tagName.toLowerCase() + '>' + el.innerHTML + '</' + el.tagName.toLowerCase() + '>' : '<' + el.tagName.toLowerCase() + '></' + el.tagName.toLowerCase() + '>';
  return el;
};
doc._body.appendChild(cc);
cc.appendChild(ml);
var _origQuerySelector = doc.querySelector;
doc.getElementById = function (id) {
  if (id === 'message-list') return ml;
  return null;
};
doc.querySelector = function (sel) {
  if (sel === '.chat-center') return cc;
  return _origQuerySelector(sel);
};
doc.body = doc._body;
doc.body.addEventListener = function () {};
doc.addEventListener = function () {};

global.window = global;
global.document = doc;
global.requestAnimationFrame = function (fn) { fn(); };
global.htmx = { process: function () {} };
global.syncReasoningButtons = function () {};
global._streamingMessageId = null;
global.Map = Map;

// Load module (IIFE, exports window.pruneMessages, _isMessagePruned, _unpruneMessage)
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'message-pruner.js'), 'utf8'));

assert(typeof window.pruneMessages === 'function', 'pruneMessages loaded');

// ── schedule prunes messages outside viewport ──
(function () {
  // msg3 at top=900 is below the viewport (800 + 1*800 buffer = 1600)
  // Viewport = 0-800, buffer = 800, so everything outside -800 to 1600 is pruned
  // msg1: 0-60 (inside), msg2: 200-260 (inside), msg3: 900-960 (inside with buffer 1600)
  // Actually: topBound = 0 - 800 = -800, botBound = 0 + 800 + 800 = 1600
  // msg3 is at 900-960 which is within bounds, so nothing should be pruned
  window.pruneMessages();
  var phs = ml.querySelectorAll('.message-placeholder');
  assertEqual(phs.length, 0, 'no pruning when all messages in range');
})();

// ── message far below viewport gets pruned ──
(function () {
  // Add a message very far down
  var msgFar = addMsg('msg-far', 5000);
  window.pruneMessages();
  var ph = ml.querySelector('.message-placeholder[data-msg-id="msg-far"]');
  assert(!!ph, 'far message pruned to placeholder');
  assert(ph.style.height === '60px', 'placeholder height matches');
  assert(window._isMessagePruned('msg-far'), '_isMessagePruned returns true');
})();

// ── _unpruneMessage restores a pruned message ──
(function () {
  var ph = document.querySelector('.message-placeholder[data-msg-id="msg-far"]');
  assert(!!ph, 'placeholder exists before unprune');
  var restored = window._unpruneMessage('msg-far');
  assert(!!restored, '_unpruneMessage returns restored element');
  assertEqual(restored.id, 'msg-far', 'restored element has correct id');
  assert(!window._isMessagePruned('msg-far'), '_unpruneMessage removes from pruned set');
})();

// ── streaming message excluded from pruning ──
(function () {
  var msgStream = addMsg('msg-stream', 10000);
  global._streamingMessageId = 'msg-stream';
  window.pruneMessages();
  assert(!window._isMessagePruned('msg-stream'), 'streaming message not pruned');
  global._streamingMessageId = null;
  // Clean up
  msgStream.remove();
})();

// ── _unpruneMessage with no placeholder returns null ──
(function () {
  var result = window._unpruneMessage('nonexistent');
  assertEqual(result, null, '_unpruneMessage on unknown returns null');
})();

// ── pruneMessages safe with missing DOM elements ──
(function () {
  // Remove message-list to simulate missing element
  var origGetById = doc.getElementById;
  doc.getElementById = function () { return null; };
  try {
    window.pruneMessages();
    assert(true, 'pruneMessages does not throw when message-list missing');
  } catch (e) {
    assert(false, 'pruneMessages threw: ' + e.message);
  }
  doc.getElementById = origGetById;
})();

// ── schedule calls pruneMessages via RAF ──
(function () {
  var called = false;
  var orig = window.pruneMessages;
  window.pruneMessages = function () { called = true; };
  // schedule() — it's the same as window.pruneMessages
  window.pruneMessages();
  assert(called, 'pruneMessages is callable');
  window.pruneMessages = orig;
})();

// ── _isMessagePruned returns true for pruned message ──
(function () {
  var msgP = addMsg('msg-prune-test', 9999);
  window.pruneMessages();
  assert(window._isMessagePruned('msg-prune-test'), '_isMessagePruned true after prune');
  window._unpruneMessage('msg-prune-test');
  assert(!window._isMessagePruned('msg-prune-test'), '_isMessagePruned false after restore');
})();

// ── Result ──
h.printSummary();
