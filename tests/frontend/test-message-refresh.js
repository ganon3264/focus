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
    fs.readFileSync(path.join(__dirname, '..', '..', 'static/js/messages/message-identity.js'), 'utf8'),
    sandbox,
  );
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

// 7. Full reconcile replaces live nodes (incl. the streaming skeleton) even
//    when pruned placeholders exist. Regression: placeholders are keyed by bare
//    id, orderedIds are DOM ids, and the full-replace path must convert back to
//    bare ids before calling _replaceMessageNode.
(function () {
  var doc = h.createMockDocument();

  function styled(tag) {
    var el = h.makeElement(tag);
    el.style = { setProperty: function () {}, removeProperty: function () {}, getPropertyValue: function () { return ''; } };
    el.replaceWith = function (n) {
      if (!this.parent) return;
      var i = this.parent.children.indexOf(this);
      if (i >= 0) this.parent.children.splice(i, 1, n);
      n.parent = this.parent;
    };
    return el;
  }
  function phFor(id) {
    var p = styled('div');
    p.classList.add('message-placeholder');
    p.dataset.msgId = id;
    return p;
  }
  function msg(id) {
    var m = styled('div');
    m.classList.add('message');
    m.id = id;
    return m;
  }

  var container = styled('div');
  container.id = 'message-list';
  var data = styled('div');
  data.id = 'message-list-data';
  container.appendChild(data);
  container.appendChild(phFor('1'));          // pruned, bare key
  container.appendChild(phFor('2'));
  var skeleton = msg('message-3');            // live streaming skeleton
  container.appendChild(skeleton);
  var sentinel = styled('div');
  sentinel.id = 'scroll-sentinel';
  container.appendChild(sentinel);
  doc._body.appendChild(container);

  var server = { 1: msg('message-1'), 2: msg('message-2'), 3: msg('message-3'), 4: msg('message-4') };
  var parsedDoc = {
    getElementById: function (id) { return server[id.replace('message-', '')] || null; },
    querySelectorAll: function (sel) {
      return sel === '.message' ? [server[1], server[2], server[3], server[4]] : [];
    },
  };

  var sandbox = {
    console: console,
    document: doc,
    DOMParser: function () { this.parseFromString = function () { return parsedDoc; }; },
    fetch: function () { return Promise.resolve({ ok: true, text: function () { return Promise.resolve('<html/>'); } }); },
    hxGet: function () { return Promise.resolve(); },
    StateManager: { get: function () { return null; } },
    htmx: { process: function () {} },
    renderMessage: function (t) { return t; },
    formatTimestamps: function () {},
    syncReasoningButtons: function () {},
    postSwapProcess: function () {},
    pruneMessages: function () {},
    _refreshChatList: function () {},
  };
  sandbox.window = sandbox;
  sandbox.window.api = { partials: { messageList: function (id) { return '/partials/message-list/' + id; } } };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, '..', '..', 'static/js/messages/message-identity.js'), 'utf8'),
    sandbox,
  );
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, '..', '..', 'static/js/messages/message-refresh.js'), 'utf8'),
    sandbox,
  );

  sandbox.window.refreshMessagesAfterStream('chat-1', '1', '3').then(function () {
    check(doc.getElementById('message-3') === server[3], 'skeleton replaced by the server node');
    check(doc.getElementById('message-3') !== skeleton, 'skeleton node is no longer attached');
    check(container.querySelectorAll('.message-placeholder').length === 0, 'pruned placeholders replaced');
    check(doc.getElementById('message-4') === server[4], 'genuinely missing message is inserted');
    check(container.children[container.children.length - 1] === sentinel, 'sentinel stays last');
    console.log('\n' + (failures === 0 ? 'all passed' : failures + ' failures'));
    process.exit(failures > 0 ? 1 : 0);
  }).catch(function (e) {
    console.error('FAIL: reconcile threw: ' + e.message);
    process.exit(1);
  });
})();
