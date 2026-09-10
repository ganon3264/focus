// Unit tests for message-identity.js — the single source of truth for how a
// message id maps between its three representations (bare, DOM id, placeholder).
var fs = require('fs');
var path = require('path');
var vm = require('vm');
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var doc = h.createMockDocument();

var sandbox = { console: console, document: doc };
sandbox.window = sandbox;
vm.createContext(sandbox);
vm.runInContext(
  fs.readFileSync(path.join(__dirname, '..', '..', 'static/js/messages/message-identity.js'), 'utf8'),
  sandbox,
);
var id = sandbox.window.MessageIdentity;
assert(id, 'MessageIdentity exported');

// ── bare(): normalizes strings, DOM ids, and elements ──
assertEqual(id.bare('message-123'), '123', 'strips the message- prefix from a string');
assertEqual(id.bare('123'), '123', 'leaves a bare string alone');
assertEqual(id.bare(null), null, 'null stays null');
assertEqual(id.bare(undefined), null, 'undefined stays null');

var node = h.makeElement('div');
node.id = 'message-abc';
assertEqual(id.bare(node), 'abc', 'reads the id off a DOM node');

var withDataset = h.makeElement('div');
withDataset.id = 'message-abc';
withDataset.dataset.messageId = 'from-dataset';
assertEqual(id.bare(withDataset), 'from-dataset', 'prefers data-message-id over the id');

var placeholder = h.makeElement('div');
placeholder.classList.add('message-placeholder');
placeholder.dataset.msgId = 'stub-id';
assertEqual(id.bare(placeholder), 'stub-id', 'reads data-msg-id off a placeholder');

// ── domId(): derives the DOM id ──
assertEqual(id.domId('123'), 'message-123', 'bare id → DOM id');
assertEqual(id.domId('message-123'), 'message-123', 'already-prefixed id is idempotent');
assertEqual(id.domId(null), null, 'null has no DOM id');

// ── node() / placeholder() lookups ──
doc.body.appendChild(node);
assert(id.node('abc') === node, 'node() finds #message-<id>');
assert(id.node('message-abc') === node, 'node() accepts a prefixed id');
assertEqual(id.node('missing'), null, 'node() returns null when absent');

var stub = h.makeElement('div');
stub.classList.add('message-placeholder');
stub.dataset.msgId = 'abc';
doc.body.appendChild(stub);
assert(id.placeholder('abc') === stub, 'placeholder() finds the stub');
assert(id.placeholder('message-abc') === stub, 'placeholder() accepts a prefixed id');
assertEqual(id.placeholder('missing'), null, 'placeholder() returns null when absent');

// placeholders are bare-keyed; a stub carrying a prefixed data-msg-id is not
// the canonical form and is deliberately not matched.
var prefixedStub = h.makeElement('div');
prefixedStub.classList.add('message-placeholder');
prefixedStub.dataset.msgId = 'message-xyz';
doc.body.appendChild(prefixedStub);
assertEqual(id.placeholder('xyz'), null, 'prefixed-keyed stub is not recognized as canonical');

console.log('\n');
h.printSummary();
