// Unit tests for the server-authoritative ordering helper in message-refresh.js.
//
// _reconcileOrder is the piece that rearranges the DOM to match the order the
// server rendered (messages ordered by `position`). It is tested directly so
// the suite does not need a DOMParser mock.
var fs = require('fs');
var path = require('path');
var vm = require('vm');
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var failures = 0;
function check(cond, msg) {
  if (cond) console.log('OK:   ' + msg);
  else { failures++; console.error('FAIL: ' + msg); }
}

function makeSandbox() {
  var sandbox = {
    console: console,
    document: h.createMockDocument(),
    fetch: function () { return Promise.resolve({ ok: false }); },
    hxGet: function () { return Promise.resolve(); },
    StateManager: { get: function () { return null; } },
  };
  sandbox.window = sandbox;
  sandbox.window.api = { partials: { messageList: function (id) { return '/partials/message-list/' + id; } } };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, '..', '..', 'static/js/messages/message-refresh.js'), 'utf8'),
    sandbox,
  );
  return sandbox;
}

function makeContainer(ids) {
  var container = h.makeElement('div');
  container.id = 'message-list';

  var data = h.makeElement('div');
  data.id = 'message-list-data';
  container.appendChild(data);

  var map = {};
  ids.forEach(function (id) {
    var msg = h.makeElement('div');
    msg.id = id;
    msg.classList.add('message');
    container.appendChild(msg);
    map[id] = msg;
  });

  var sentinel = h.makeElement('div');
  sentinel.id = 'scroll-sentinel';
  container.appendChild(sentinel);

  return { container: container, data: data, sentinel: sentinel, map: map };
}

function ids(container) {
  return Array.prototype.map.call(container.children, function (el) { return el.id; }).join(',');
}

var sandbox = makeSandbox();
var reconcile = sandbox.window._reconcileOrder;

// 1. Reorder to match the server
(function () {
  var t = makeContainer(['message-a', 'message-b', 'message-c']);
  reconcile(
    t.container,
    ['message-c', 'message-a', 'message-b'],
    t.data,
    t.sentinel,
    function (id) { return t.map[id]; },
    function () { return null; },
  );
  assertEqual(
    ids(t.container),
    'message-list-data,message-c,message-a,message-b,scroll-sentinel',
    'nodes are reordered to the server order',
  );
})();

// 2. Insert a node the DOM is missing
(function () {
  var t = makeContainer(['message-a', 'message-c']);
  var newB = h.makeElement('div');
  newB.id = 'message-b';
  newB.classList.add('message');

  var inserted = reconcile(
    t.container,
    ['message-a', 'message-b', 'message-c'],
    t.data,
    t.sentinel,
    function (id) { return t.map[id]; },
    function (id) { return id === 'message-b' ? newB : null; },
  );
  assertEqual(ids(t.container), 'message-list-data,message-a,message-b,message-c,scroll-sentinel',
    'missing node is inserted in position');
  assertEqual(inserted.length, 1, 'inserted nodes are returned for post-processing');
  check(inserted[0] === newB, 'returned node is the one that was inserted');
})();

// 3. Drop a node the server no longer has
(function () {
  var t = makeContainer(['message-a', 'message-b', 'message-c']);
  reconcile(
    t.container,
    ['message-a', 'message-c'],
    t.data,
    t.sentinel,
    function (id) { return t.map[id]; },
    function () { return null; },
  );
  assertEqual(ids(t.container), 'message-list-data,message-a,message-c,scroll-sentinel',
    'extra node is removed');
})();

// 4. Keep a pruned placeholder in place while it is still wanted
(function () {
  var t = makeContainer(['message-a', 'message-b']);
  var ph = h.makeElement('div');
  ph.classList.add('message-placeholder');
  ph.dataset.msgId = 'b';
  t.container.insertBefore(ph, t.map['message-b']);
  t.map['message-b'].remove();

  reconcile(
    t.container,
    ['message-a', 'message-b'],
    t.data,
    t.sentinel,
    function (id) {
      if (id === 'message-b') {
        return t.container.querySelector('.message-placeholder[data-msg-id="b"]');
      }
      return t.map[id];
    },
    function () { return null; },
  );
  assertEqual(ids(t.container), 'message-list-data,message-a,,scroll-sentinel',
    'placeholder is kept in the right slot');
  check(t.container.children[2].classList.contains('message-placeholder'),
    'kept node is still the placeholder');
})();

// 5. Remove a placeholder for a message the server dropped
(function () {
  var t = makeContainer(['message-a']);
  var ph = h.makeElement('div');
  ph.classList.add('message-placeholder');
  ph.dataset.msgId = 'gone';
  t.container.appendChild(ph);

  reconcile(
    t.container,
    ['message-a'],
    t.data,
    t.sentinel,
    function (id) { return t.map[id]; },
    function () { return null; },
  );
  assertEqual(t.container.querySelectorAll('.message-placeholder').length, 0,
    'placeholder for a deleted message is removed');
})();

// 6. Sentinel is forced last
(function () {
  var t = makeContainer(['message-a', 'message-b']);
  t.container.insertBefore(t.sentinel, t.map['message-b']);
  reconcile(
    t.container,
    ['message-a', 'message-b'],
    t.data,
    t.sentinel,
    function (id) { return t.map[id]; },
    function () { return null; },
  );
  assertEqual(ids(t.container), 'message-list-data,message-a,message-b,scroll-sentinel',
    'sentinel is moved back to the end');
})();

console.log('\n' + (failures === 0 ? 'all passed' : failures + ' failures'));
process.exit(failures > 0 ? 1 : 0);
