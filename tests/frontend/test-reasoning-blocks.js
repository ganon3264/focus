// Unit tests for message-builder.js reasoning segment structure.
//
// Index 0 (pre-answer reasoning) is a plain div — it cannot be <details>
// because streaming writes into it — and it has no head: the message rail's
// toggle controls it. Later blocks (post-tool) are <details>.
//
// The markup itself comes from the server-rendered templates fixture (see
// fixtures/message-templates.html, kept in sync by
// test_message_template.py::test_message_templates_fixture_is_current) — these
// tests only assert the cloned result.

var h = require('./helpers.js');
var assert = h.assert;
var path = require('path');
var fs = require('fs');

var doc = h.createMockDocument();
global.window = global;
global.document = doc;
global.navigator = { clipboard: { writeText: function () {} } };
global.URL = { createObjectURL: function () { return 'blob:x'; } };
window.getSvgSprite = function () { return '<svg></svg>'; };
window.renderMessage = function (text) { return text; };

h.installTemplates(doc, fs.readFileSync(path.join(__dirname, 'fixtures', 'message-templates.html'), 'utf8'));

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'message-builder.js'), 'utf8'));

// 1. First reasoning block is a headless div with hidden content
(function () {
  var block = window.segmentBuilders.reasoning(0);
  assert(block.tagName === 'DIV', 'index 0 reasoning block is a div');
  assert(block.dataset.ui === 'reasoning-block', 'index 0 block carries the reasoning-block hook');
  assert(block.classList.contains('reasoning-block'), 'index 0 block keeps its styling class');
  var content = block.querySelector('[data-ui~="reasoning-content"]');
  assert(content && content.classList.contains('hidden'),
    'index 0 content starts hidden');
  assert(block.querySelector('[data-ui="reasoning-toggle-btn"]') === null,
    'index 0 block carries no toggle of its own');
})();

// 2. Subsequent reasoning blocks are collapsible details
(function () {
  var block = window.segmentBuilders.reasoning(1);
  assert(block.tagName === 'DETAILS', 'index 1 reasoning block is a details');
  assert(!!block.querySelector('summary'), 'index 1 block has a summary toggle');
  assert(block.getAttribute('data-think-id') === '1', 'index 1 block carries its think id');
})();

h.printSummary();
