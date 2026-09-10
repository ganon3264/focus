// Contract tests for post-process.js — the single post-render pass for messages.
var fs = require('fs');
var path = require('path');
var vm = require('vm');
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var doc = h.createMockDocument();
doc.body.addEventListener = function () {};

var calls = { htmx: 0, sync: 0, format: 0, send: 0, sentinel: 0 };

var sandbox = {
  console: console,
  document: doc,
  StateManager: { get: function () { return null; } },
  htmx: { process: function () { calls.htmx++; } },
  renderMessage: function (t) { return '<rendered>' + (t || '') + '</rendered>'; },
  syncReasoningButtons: function () { calls.sync++; },
  formatTimestamps: function () { calls.format++; },
  updateSendButtonState: function () { calls.send++; },
  ensureSentinelAndObserver: function () { calls.sentinel++; },
};
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(
  fs.readFileSync(path.join(__dirname, '..', '..', 'static/js/messages/post-process.js'), 'utf8'),
  sandbox,
);

var process = sandbox.window.processMessageList;
assert(typeof process === 'function', 'processMessageList exported');

function makeContainer() {
  var container = h.makeElement('div');
  container.id = 'message-list';

  var md = h.makeElement('div');
  md.classList.add('markdown-content');
  md.textContent = 'hello';
  container.appendChild(md);

  var message = h.makeElement('div');
  message.classList.add('message');
  var cb = h.makeElement('div');
  cb.classList.add('delete-mode-checkbox');
  cb.classList.add('hidden');
  message.appendChild(cb);
  var actions = h.makeElement('div');
  actions.classList.add('normal-mode-actions');
  message.appendChild(actions);
  container.appendChild(message);

  return { container: container, md: md, cb: cb, actions: actions };
}

// ── outside delete mode: renders content, leaves checkboxes hidden ──
(function () {
  var t = makeContainer();
  process(t.container);
  assert(calls.htmx === 1, 'htmx.process is applied to new nodes');
  assert(t.md.classList.contains('processed'), 'unprocessed markdown is rendered');
  assertEqual(t.md.innerHTML, '<rendered>hello</rendered>', 'rendered markup is written in place');
  assert(calls.sync === 1, 'reasoning buttons are synced');
  assert(calls.format === 1, 'timestamps are formatted');
  assert(t.cb.classList.contains('hidden'), 'checkboxes stay hidden outside delete mode');
  assert(calls.send === 1, 'send button state is updated');
  assert(calls.sentinel === 1, 'sentinel observer is ensured');
})();

// ── inside delete mode: reveals checkboxes and hides normal actions ──
(function () {
  var toolbar = h.makeElement('div');
  toolbar.id = 'delete-toolbar';
  doc.body.appendChild(toolbar);

  var t = makeContainer();
  process(t.container);
  assert(!t.cb.classList.contains('hidden'), 'checkboxes are revealed in delete mode');
  assert(t.actions.classList.contains('hidden'), 'normal actions are hidden in delete mode');

  toolbar.classList.add('hidden');
})();

// ── missing container is a no-op ──
(function () {
  var before = calls.htmx;
  process(null);
  assertEqual(calls.htmx, before, 'null container does not process');
})();

console.log('\n');
h.printSummary();
