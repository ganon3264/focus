// Unit tests for scroll-manager.js — the chat's pinned-bottom state machine.
// The module owns one measurement (distance from the bottom) and one action
// (pin), so a scenario is just: set the scroller's geometry, fire the trigger
// that the browser would fire (resize observer / scroll), read the result.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var path = require('path');
var fs = require('fs');

var SRC = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'scroll-manager.js'), 'utf8');

// ── DOM: a scroller with a list inside it ──
var list = h.makeElement('div');
list.id = 'message-list';

var scroller = h.makeElement('div');
scroller.className = 'chat-center';
scroller.dataset.ui = 'chat-center';
scroller.appendChild(list);

var doc = h.createMockDocument();
doc._body.appendChild(scroller);
doc.getElementById = function (id) {
  return id === 'message-list' ? list : null;
};
doc.querySelector = function (sel) {
  return sel === '[data-ui="chat-center"]' ? scroller : null;
};

// ── Scroller geometry ──
scroller.scrollTop = 0;
scroller.clientHeight = 800;
scroller.scrollHeight = 800;
var pins = [];
scroller.scrollTo = function (opts) {
  pins.push(opts.top);
  // Like a browser: the offset clamps to the scrollable range.
  scroller.scrollTop = Math.max(0, Math.min(opts.top, scroller.scrollHeight - scroller.clientHeight));
};
var scrollHandler = null;
scroller.addEventListener = function (name, fn) {
  if (name === 'scroll') scrollHandler = fn;
};

global.document = doc;
global.window = global;
global.location = { search: '' };
global.URLSearchParams = URLSearchParams;
global.Prefs = { get: function () { return 'pinned'; } };

var MockRO = h.createMockResizeObserver();
global.ResizeObserver = MockRO;

function load() {
  // A fresh module instance: the one-shot landing flag must start over.
  eval(SRC);
  window.ChatScroll.init();
  var instances = MockRO._instances;
  return instances[instances.length - 1];
}

// Grows the content by `delta` px, exactly as a rendered token would.
function grow(observer, delta) {
  scroller.scrollHeight += delta;
  observer._trigger();
}

// ── the first layout pass lands at the bottom ──
(function () {
  var obs = load();
  assert(!!obs, 'init observes the message list');
  pins.length = 0;
  scroller.scrollHeight = 2000;
  obs._trigger();
  assertEqual(pins.length, 1, 'the first layout pass pins');
  assertEqual(scroller.scrollTop, 1200, 'the landing scroll goes to the true bottom');
  assertEqual(window.ChatScroll.pinned(), true, 'the reader is pinned after landing');
  assertEqual(window.ChatScroll.distance(), 0, 'distance reads zero at the pin');
})();

// ── growth while pinned keeps the bottom on screen ──
(function () {
  var obs = MockRO._instances[MockRO._instances.length - 1];
  pins.length = 0;
  grow(obs, 120);
  assertEqual(pins.length, 1, 'a grown reply is followed');
  assertEqual(scroller.scrollTop, 1320, 'the follow scroll lands on the new bottom');
})();

// ── the reader scrolls away: growth must not chase them ──
(function () {
  var obs = MockRO._instances[MockRO._instances.length - 1];
  scroller.scrollTop = 800;      // wheeled up 520px
  scrollHandler();
  assertEqual(window.ChatScroll.pinned(), false, 'scrolling off the bottom unpins');

  pins.length = 0;
  grow(obs, 120);
  assertEqual(pins.length, 0, 'growth does not chase a reader who scrolled away');
  assertEqual(scroller.scrollTop, 800, 'their scroll position is untouched');
})();

// ── coming back to the bottom re-pins ──
(function () {
  var obs = MockRO._instances[MockRO._instances.length - 1];
  scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
  scrollHandler();
  assertEqual(window.ChatScroll.pinned(), true, 'scrolling back to the bottom pins again');

  pins.length = 0;
  grow(obs, 60);
  assertEqual(pins.length, 1, 'following resumes once the reader is back at the bottom');
})();

// ── `always` follows from anywhere ──
(function () {
  var obs = MockRO._instances[MockRO._instances.length - 1];
  window.ChatScroll.unpin();
  Prefs.get = function () { return 'always'; };
  pins.length = 0;
  grow(obs, 60);
  assertEqual(pins.length, 1, 'always: growth pins even after the reader scrolled away');

  Prefs.get = function () { return 'pinned'; };
  scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
  scrollHandler();
})();

// ── `disabled` never moves the view ──
(function () {
  var obs = MockRO._instances[MockRO._instances.length - 1];
  scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight;
  scrollHandler();                      // at the bottom, but the reader opted out
  Prefs.get = function () { return 'disabled'; };
  pins.length = 0;
  grow(obs, 60);
  assertEqual(pins.length, 0, 'disabled: growth is never followed, even at the bottom');

  Prefs.get = function () { return 'pinned'; };
})();

// ── unpin() is the reader declaring they are done following ──
(function () {
  var obs = MockRO._instances[MockRO._instances.length - 1];
  window.ChatScroll.unpin();
  pins.length = 0;
  grow(obs, 60);
  assertEqual(pins.length, 0, 'unpin() stops following even while the reader is at the bottom');
})();

// ── a search hit owns the landing position ──
(function () {
  location.search = '?at=msg-1';
  pins.length = 0;
  scroller.scrollHeight = 3000;
  scroller.scrollTop = 0;
  scroller.clientHeight = 800;
  var obs = load();
  obs._trigger();
  assertEqual(pins.length, 0, 'the landing pass stands down when a hit is in the URL');
  assertEqual(window.ChatScroll.pinned(), false, 'the hit position is not a bottom');
  location.search = '';
  window.ChatScroll.pin();
})();

// ── a scroller without scrollTo still pins ──
(function () {
  var saved = scroller.scrollTo;
  delete scroller.scrollTo;
  scroller.scrollTop = 0;
  window.ChatScroll.pin();
  assertEqual(scroller.scrollTop, scroller.scrollHeight, 'pin falls back to scrollTop (the browser clamps it)');
  scroller.scrollTo = saved;
})();

// ── follows() is the one predicate growth and block-opening both ask ──
(function () {
  load();
  window.ChatScroll.pin();
  Prefs.get = function () { return 'disabled'; };
  assertEqual(window.ChatScroll.follows(), false, 'disabled: nothing is followed, even at the bottom');
  Prefs.get = function () { return 'always'; };
  window.ChatScroll.unpin();
  assertEqual(window.ChatScroll.follows(), true, 'always: growth is followed from anywhere');
  Prefs.get = function () { return 'pinned'; };
  assertEqual(window.ChatScroll.follows(), false, 'pinned: false once the reader scrolled away');
  window.ChatScroll.pin();
  assertEqual(window.ChatScroll.follows(), true, 'pinned: true at the bottom');
})();

// ── init is idempotent, and re-arms on a replaced list node ──
(function () {
  var before = MockRO._instances.length;
  window.ChatScroll.init();
  assertEqual(MockRO._instances.length, before, 'init is a no-op while the nodes are unchanged');

  var replacement = h.makeElement('div');
  replacement.id = 'message-list';
  var baseGetElement = doc.getElementById;
  doc.getElementById = function (id) { return id === 'message-list' ? replacement : baseGetElement(id); };
  window.ChatScroll.init();
  var fresh = MockRO._instances[MockRO._instances.length - 1];
  assertEqual(MockRO._instances.length, before + 1, 'a replaced list is observed by a fresh observer');
  assert(fresh._elements[0] === replacement, 'the fresh observer watches the new list');

  // The fresh list lands like a fresh page (the old geometry was someone else's).
  pins.length = 0;
  scroller.scrollHeight = 2000;
  scroller.scrollTop = 0;
  fresh._trigger();
  assertEqual(pins.length, 1, 'the replacement list lands at the bottom');

  doc.getElementById = baseGetElement;
})();

// ── no ResizeObserver, no throw (and no follow, but a usable pin) ──
(function () {
  var saved = global.ResizeObserver;
  delete global.ResizeObserver;
  var other = h.makeElement('div');
  other.id = 'message-list';
  var baseGetElement = doc.getElementById;
  doc.getElementById = function (id) { return id === 'message-list' ? other : baseGetElement(id); };
  try {
    window.ChatScroll.init();
    pins.length = 0;
    window.ChatScroll.pin();
    assertEqual(pins.length, 1, 'pin still works without a ResizeObserver');
  } catch (e) {
    assert(false, 'init must not throw without a ResizeObserver: ' + e.message);
  }
  doc.getElementById = baseGetElement;
  global.ResizeObserver = saved;
})();

// ── the module is safe before init / without a chat ──
(function () {
  var noDom = h.createMockDocument();
  global.document = noDom;
  try {
    window.ChatScroll.init();
    window.ChatScroll.pin();
    window.ChatScroll.unpin();
    assert(Number.isFinite(window.ChatScroll.distance()), 'distance stays a number with no chat');
    assert(true, 'init/pin are no-ops on a page with no chat');
  } catch (e) {
    assert(false, 'unexpected throw: ' + e.message);
  }
})();

// ── Result ──
h.printSummary();
