// Unit tests for message-builder.js tool-call cards.
//
// The card is cloned from the server-rendered fixture (see
// fixtures/message-templates.html) and filled by buildToolCallCard. The fill
// hooks are data-ui attributes: `summary span` also matches the drawn caret,
// so filling by tag would pour the JSON into the caret (which is rotated 45°)
// and leave the `@@args@@` placeholder in the summary.

var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
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

function build(call) {
  var section = window.segmentBuilders.tool_calls([call]);
  return { section: section, card: section.children[0] };
}

// A call with arguments fills both hooks and leaves no placeholder behind.
(function () {
  var built = build({ id: 'call-1', name: 'read_file', arguments: '{"path":"README.md"}' });
  var card = built.card;
  assert(!!card, 'a card is built');
  assertEqual(card.getAttribute('data-call-id'), 'call-1', 'the call id lands on the card');

  var nameEl = card.querySelector('[data-ui="tool-name"]');
  assertEqual(nameEl.textContent, 'read_file', 'the name hook takes the tool name');

  var argsEl = card.querySelector('[data-ui="tool-args"]');
  assertEqual(argsEl.textContent, '{"path":"README.md"}', 'the args hook takes the arguments');

  var summary = card.querySelector('summary');
  var caret = summary.children[0];
  assert(!!caret && caret.classList.contains('caret-mark'), 'the drawn caret survives the fill');
  assertEqual(caret.textContent, '', 'the caret never receives the arguments');

  assert(summary.textContent.indexOf('@@') === -1, 'no template placeholder is left in the summary');
})();

// Empty arguments drop the meta span, not the caret.
(function () {
  var built = build({ id: 'call-2', name: 'list_dir', arguments: '{}' });
  var card = built.card;
  assertEqual(card.querySelector('[data-ui="tool-name"]').textContent, 'list_dir', 'the name still fills');
  assert(card.querySelector('[data-ui="tool-args"]') === null, 'empty args remove the meta span');
  var summary = card.querySelector('summary');
  assert(!!summary.children[0] && summary.children[0].classList.contains('caret-mark'),
    'the caret stays when there are no args');
})();

// Object arguments are stringified; the body stays closed until a result lands.
(function () {
  var built = build({ id: 'call-3', name: 'read_file', arguments: { path: 'a.txt' } });
  var card = built.card;
  assertEqual(card.querySelector('[data-ui="tool-args"]').textContent, '{"path":"a.txt"}', 'object args are stringified');

  var body = card.querySelector('[data-ui="tool-result-body"]');
  assertEqual(body.style.display, 'none', 'the result body is closed while executing');

  var img = body.querySelector('img');
  assert(!img.getAttribute('src'), 'the fixture image placeholder is cleared');
  assertEqual(img.style.display, 'none', 'the empty image stays hidden');
})();

// A tool_result opens the body and fills the pre.
(function () {
  var built = build({ id: 'call-4', name: 'read_file', arguments: '{"path":"a.txt"}' });
  var body = built.card.querySelector('[data-ui="tool-result-body"]');
  assertEqual(body.style.display, 'none', 'the body is closed until the result arrives');

  window.updateToolCallCard(built.section, 'call-4', 'hello', false, null);
  assertEqual(body.style.display, 'block', 'the body opens for a result');
  assertEqual(body.querySelector('pre').textContent, 'hello', 'the result lands in the pre');
})();

h.printSummary();
