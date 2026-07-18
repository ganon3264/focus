// Unit tests for scroll_manager.js — auto-scroll via IntersectionObserver
var h = require('./_helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var path = require('path');
var fs = require('fs');

// Build a minimal DOM for scroll-manager
var sentinel = h.makeElement('div');
sentinel.id = 'scroll-sentinel';

var messageList = h.makeElement('div');
messageList.id = 'message-list';
messageList.appendChild(sentinel);

var chatCenter = h.makeElement('div');
chatCenter.className = 'chat-center';
chatCenter.id = 'chat-center';
chatCenter.appendChild(messageList);

var doc = h.createMockDocument();
doc._body.appendChild(chatCenter);
doc.getElementById = function (id) {
  if (id === 'scroll-sentinel') return sentinel;
  if (id === 'message-list') return messageList;
  return null;
};
doc.querySelector = function (sel) {
  if (sel === '.chat-center') return chatCenter;
  if (sel === '#message-list') return messageList;
  return null;
};

global.document = doc;
global.window = global;
global.performance = { getEntriesByType: function () { return [{ type: 'navigate' }]; } };
global.requestAnimationFrame = function (fn) { fn(); };

// IntersectionObserver mock
var MockIO = h.createMockIntersectionObserver();
global.IntersectionObserver = MockIO;

// Load module (sets window.autoScroll=true, window.scrollSentinel=null initially)
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'scroll_manager.js'), 'utf8'));

// ── autoScroll initial value ──
(function () {
  assertEqual(window.autoScroll, true, 'autoScroll initial true');
})();

// ── ensureSentinelAndObserver creates sentinel if missing ──
(function () {
  document.getElementById('scroll-sentinel').remove();
  window.ensureSentinelAndObserver();
  var newSentinel = document.getElementById('scroll-sentinel');
  assert(!!newSentinel, 'ensureSentinelAndObserver creates sentinel if missing');
  // Re-add for other tests
  var s = h.makeElement('div');
  s.id = 'scroll-sentinel';
  messageList.appendChild(s);
})();

// ── ensureSentinelAndObserver repositions sentinel as last child ──
(function () {
  // Add a child after sentinel to force reposition
  var extra = h.makeElement('div');
  messageList.appendChild(extra);
  window.ensureSentinelAndObserver();
  var listChildren = messageList.children;
  var last = listChildren[listChildren.length - 1];
  assertEqual(last && last.id, 'scroll-sentinel', 'sentinel repositioned as last child');
  extra.remove();
})();

// ── IntersectionObserver is created ──
(function () {
  var prevLen = MockIO._instances.length;
  window.ensureSentinelAndObserver();
  assert(MockIO._instances.length >= 1, 'IntersectionObserver created');
})();

// ── autoScroll toggled by IntersectionObserver callback ──
(function () {
  window.ensureSentinelAndObserver();
  var obs = MockIO._instances[MockIO._instances.length - 1];
  obs && obs._trigger([{ isIntersecting: true, target: sentinel }]);
  assertEqual(window.autoScroll, true, 'autoScroll set to true when sentinel visible');

  obs._trigger([{ isIntersecting: false, target: sentinel }]);
  assertEqual(window.autoScroll, false, 'autoScroll set to false when sentinel leaves viewport');
})();

// ── ensureSentinelAndObserver is safe when message-list missing ──
(function () {
  var ml = document.getElementById('message-list');
  ml.remove();
  try {
    window.ensureSentinelAndObserver();
    assert(true, 'ensureSentinelAndObserver with no message-list does not throw');
  } catch (e) {
    assert(false, 'unexpected throw: ' + e.message);
  }
  messageList.remove = function () { messageList.parent = null; };
})();

// ── Result ──
h.printSummary();
