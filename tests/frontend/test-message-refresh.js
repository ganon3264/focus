// Tests for message-refresh.js — the in-place list reconcile, driven only
// through the public entry points (refreshMessagesAfterStream /
// refreshChatMessages). Every assertion reads the rendered list.
var fs = require('fs');
var path = require('path');
var vm = require('vm');
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var ROOT = path.join(__dirname, '..', '..');

function makeEnv(clientItems) {
  var doc = h.createMockDocument();

  function styled(tag) {
    var el = h.makeElement(tag);
    el.style = {
      setProperty: function () {},
      removeProperty: function () {},
      getPropertyValue: function () { return ''; },
    };
    el.replaceWith = function (n) {
      if (!this.parent) return;
      var i = this.parent.children.indexOf(this);
      if (i >= 0) this.parent.children.splice(i, 1, n);
      n.parent = this.parent;
    };
    return el;
  }
  doc.createElement = function (tag) { return styled(tag); };

  var container = styled('div');
  container.id = 'message-list';
  var dataDiv = styled('div');
  dataDiv.id = 'message-list-data';
  container.appendChild(dataDiv);
  doc._body.appendChild(container);

  var clientNodes = {};
  var clientPlaceholders = {};
  clientItems.forEach(function (item) {
    var el = styled('div');
    if (typeof item === 'string') {
      el.id = 'message-' + item;
      el.dataset.ui = 'message';
      clientNodes[item] = el;
    } else {
      el.dataset.ui = 'message-placeholder';
      el.dataset.msgId = item.placeholder;
      clientPlaceholders[item.placeholder] = el;
    }
    container.appendChild(el);
  });

  var env = {
    doc: doc,
    container: container,
    clientNodes: clientNodes,
    clientPlaceholders: clientPlaceholders,
    processCalls: 0,
    reapplyCalls: 0,
    reopened: [],
    fetchUrls: [],
    server: null,
  };

  // *rendered* is what a narrowed response actually carries (default: every
  // listed message), the order is always the full position order.
  env.serve = function (order, rendered) {
    var carried = rendered || order;
    var nodes = {};
    carried.forEach(function (id) {
      var n = styled('div');
      n.id = 'message-' + id;
      n.dataset.ui = 'message';
      nodes[id] = n;
    });
    var serverData = styled('div');
    serverData.id = 'message-list-data';
    serverData.dataset.order = order.map(function (id) { return 'message-' + id; }).join(',');
    env.server = { order: order, carried: carried, nodes: nodes, data: serverData };
    return env.server;
  };

  env.serverDoc = function () {
    return {
      getElementById: function (id) {
        if (id === 'message-list-data') return env.server.data;
        var bare = id.indexOf('message-') === 0 ? id.slice('message-'.length) : id;
        return env.server.nodes[bare] || null;
      },
      querySelectorAll: function (sel) {
        if (sel !== '[data-ui="message"]') return [];
        return env.server.carried.map(function (id) { return env.server.nodes[id]; });
      },
    };
  };

  env.sequence = function () {
    return container.children.map(function (el) {
      if (el.id) return el.id;
      if (el.dataset.ui === 'message-placeholder') return 'placeholder:' + el.dataset.msgId;
      return el.tagName.toLowerCase();
    }).join(',');
  };

  env.node = function (id) { return doc.getElementById('message-' + id); };
  env.placeholders = function () {
    return container.querySelectorAll('[data-ui="message-placeholder"]');
  };

  var sandbox = {
    console: console,
    document: doc,
    DOMParser: function () {
      this.parseFromString = function () { return env.serverDoc(); };
    },
    fetch: function (url) {
      return Promise.resolve({
        ok: true,
        text: function () { return Promise.resolve('<html/>'); },
        json: function () { return Promise.resolve({}); },
      });
    },
    hxGet: function () { return Promise.resolve(); },
    StateManager: { get: function () { return null; } },
    htmx: { process: function () {} },
    renderMessage: function (t) { return t; },
    formatTimestamps: function () {},
    syncReasoningButtons: function () {},
    pruneMessages: function () {},
    processMessageList: function () { env.processCalls++; },
    reapplyDeleteMode: function () { env.reapplyCalls++; },
    reasoningStaysOpen: function () { return false; },
    setReasoningOpen: function (node, open) { env.reopened.push(node.id + ':' + open); },
  };
  sandbox.window = sandbox;
  sandbox.addEventListener = function () {};
  sandbox.removeEventListener = function () {};
  sandbox.hxFetch = function (url) {
    env.fetchUrls.push(url);
    return sandbox.fetch(url);
  };
  sandbox.window.api = {
    partials: {
      messageList: function (id, changed) {
        return '/partials/message-list/' + id + (changed ? '?ids=' + changed.join(',') : '');
      },
    },
  };

  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, 'static/js/messages/message-identity.js'), 'utf8'),
    sandbox,
  );
  vm.runInContext(
    fs.readFileSync(path.join(ROOT, 'static/js/messages/message-refresh.js'), 'utf8'),
    sandbox,
  );
  env.window = sandbox.window;
  return env;
}

async function reordersLiveNodes() {
  var env = makeEnv(['1', '2', '3']);
  env.serve(['3', '1', '2']);
  await env.window.refreshMessagesAfterStream('chat-1', '3', '2');
  assertEqual(env.sequence(), 'message-list-data,message-3,message-1,message-2',
    'live nodes end up in the server position order');
  assertEqual(env.placeholders().length, 0, 'reordering prunes nothing');
}

async function insertsMissingMessage() {
  var env = makeEnv(['1', '2']);
  var server = env.serve(['1', '2', '3']);
  await env.window.refreshMessagesAfterStream('chat-1', null, '3');
  assertEqual(env.sequence(), 'message-list-data,message-1,message-2,message-3',
    'a message the client never had is inserted in position');
  assert(env.node('3') === server.nodes['3'], 'inserted node is the server node');
  assertEqual(env.processCalls, 1, 'inserted list is post-processed once');
}

async function dropsVanishedMessage() {
  var env = makeEnv(['1', '2', '3']);
  var kept3 = env.clientNodes['3'];
  env.serve(['1', '3']);
  await env.window.refreshMessagesAfterStream('chat-1', '1', null);
  assertEqual(env.sequence(), 'message-list-data,message-1,message-3',
    'a message the server no longer lists is dropped from the list');
  assert(env.node('3') === kept3, 'unchanged neighbour keeps its live node');
}

async function keepsWantedPlaceholders() {
  var env = makeEnv(['1', { placeholder: '2' }, '3', { placeholder: 'gone' }]);
  env.serve(['1', '2', '3'], ['1', '3']);
  await env.window.refreshMessagesAfterStream('chat-1', '1', '3');
  assertEqual(env.sequence(), 'message-list-data,message-1,placeholder:2,message-3',
    'a still-listed pruned message keeps its placeholder in its slot');
  assertEqual(env.placeholders().length, 1, 'a placeholder for a deleted message is removed');
  assert(env.placeholders()[0] === env.clientPlaceholders['2'], 'kept stub is the original placeholder');
}

async function replacesNodesThroughFullRefresh() {
  var env = makeEnv([{ placeholder: '1' }, { placeholder: '2' }, '3']);
  var skeleton = env.clientNodes['3'];
  var server = env.serve(['1', '2', '3', '4']);

  await env.window.refreshMessagesAfterStream('chat-1', '1', '3');
  assert(env.node('3') === server.nodes['3'], 'streaming skeleton replaced by the server node');
  assert(env.node('3') !== skeleton, 'skeleton node is no longer attached');
  assertEqual(env.placeholders().length, 0, 'pruned placeholders replaced by live nodes');
  assertEqual(env.sequence(), 'message-list-data,message-1,message-2,message-3,message-4',
    'genuinely missing message is inserted at the end');
  assertEqual(env.processCalls, 1, 'the single processing pass runs once');
  assertEqual(env.reapplyCalls, 1, 'delete mode is re-applied by the renderer');

  var server3b = env.serve(['1', '2', '3', '4']);
  env.processCalls = 0;
  env.reapplyCalls = 0;
  await env.window.refreshChatMessages('chat-1');
  assert(env.node('3') === server3b.nodes['3'], 'refreshChatMessages uses the reconcile renderer');
  assertEqual(env.processCalls, 1, 'full reload also runs exactly one processing pass');
  assertEqual(env.reapplyCalls, 1, 'full reload re-applies delete mode');
}

async function carriesReasoningOpenState() {
  var env = makeEnv(['1']);
  env.serve(['1', '2']);
  await env.window.refreshChatMessages('chat-1');
  env.node('2').classList.add('reasoning-open');
  env.reopened.length = 0;

  await env.window.refreshMessagesAfterStream('chat-1', null, '2');
  assertEqual(env.reopened.length, 0, 'a folded preference leaves the server node folded');

  env.serve(['1', '2']);
  await env.window.refreshChatMessages('chat-1');
  env.node('2').classList.add('reasoning-open');
  env.window.reasoningStaysOpen = function () { return true; };
  env.reopened.length = 0;
  await env.window.refreshMessagesAfterStream('chat-1', null, '2');
  assertEqual(env.reopened.length, 1, 'the open block is reopened once');
  assertEqual(env.reopened[0], 'message-2:true', 'the reopened node is the replacement');
}

(async function () {
  var steps = [
    reordersLiveNodes,
    insertsMissingMessage,
    dropsVanishedMessage,
    keepsWantedPlaceholders,
    replacesNodesThroughFullRefresh,
    carriesReasoningOpenState,
  ];
  for (var i = 0; i < steps.length; i++) {
    try {
      await steps[i]();
    } catch (e) {
      assert(false, steps[i].name + ' threw: ' + e.message);
    }
  }
  h.printSummary();
})();
