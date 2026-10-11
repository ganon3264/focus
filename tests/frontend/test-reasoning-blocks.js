// Unit tests for message-builder.js reasoning segment structure.
//
// Index 0 (pre-answer reasoning) is a plain div controlled by the message-level
// meta toggle; it must not grow its own control. Later blocks (post-tool) are
// <details>/<summary> disclosures.

var h = require('./helpers.js');
var assert = h.assert;
var makeElement = h.makeElement, querySelectorAll = h.querySelectorAll;

var path = require('path');
var fs = require('fs');

var root = makeElement('body');
global.document = {
  _root: root,
  querySelector: function (sel) { return querySelectorAll(root, sel)[0] || null; },
  querySelectorAll: function (sel) { return querySelectorAll(root, sel); },
  addEventListener: function () {},
  createElement: function (tag) { return makeElement(tag); },
  createTextNode: function (text) { var el = makeElement('span'); el._textContent = text; return el; },
};
root.tagName = 'BODY';

global.window = global;
global.navigator = { clipboard: { writeText: function () {} } };
window.getSvgSprite = function () { return '<svg></svg>'; };

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'message-builder.js'), 'utf8'));

// 1. First reasoning block is a div with hidden content and no own toggle
(function () {
  var block = window.segmentBuilders.reasoning(0);
  assert(block.tagName === 'DIV', 'index 0 reasoning block is a div');
  assert(block.classList.contains('reasoning-block'), 'index 0 block has reasoning-block class');
  var content = block.querySelector('.reasoning-content');
  assert(content && content.classList.contains('hidden'),
    'index 0 content starts hidden');
  assert(block.querySelector('.reasoning-toggle-btn') === null,
    'index 0 block does not carry its own toggle');
})();

// 2. Subsequent reasoning blocks are collapsible details
(function () {
  var block = window.segmentBuilders.reasoning(1);
  assert(block.tagName === 'DETAILS', 'index 1 reasoning block is a details');
  assert(!!block.querySelector('summary'), 'index 1 block has a summary toggle');
})();

h.printSummary();
