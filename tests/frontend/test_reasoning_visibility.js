// Unit tests for reasoning_utils.js — loaded from source with DOM mocks
var h = require('./_helpers.js');
var assert = h.assert, assertNotIncludes = h.assertNotIncludes;
var makeElement = h.makeElement, querySelectorAll = h.querySelectorAll;

var path = require('path');
var fs = require('fs');

// Shared document mock that survives module load
var root = makeElement('body');
global.document = {
  _root: root,
  querySelector: function (sel) { return querySelectorAll(root, sel)[0] || null; },
  querySelectorAll: function (sel) { return querySelectorAll(root, sel); },
  addEventListener: function () {},
  createElement: function (tag) { return makeElement(tag); },
};
root.tagName = 'BODY';

global.window = global;
global.navigator = { clipboard: { writeText: function () {} } };

// Load the actual module — it registers _updateReasoningButton, syncReasoningButtons, preserveOpenStates on window
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'reasoning_utils.js'), 'utf8'));

// ── Helpers ──

function makeMessage(opts) {
  opts = opts || {};
  var msg = makeElement('div');
  msg.classList.add('message');

  var btn = makeElement('button');
  btn.classList.add('reasoning-toggle-btn');
  if (opts.buttonHiddenInitially) btn.classList.add('hidden');
  msg.appendChild(btn);

  var content = makeElement('div');
  content.classList.add('message-content');
  if (opts.withReasoning) {
    var details = makeElement('details');
    details.classList.add('reasoning');
    content.appendChild(details);
  }
  msg.appendChild(content);

  return msg;
}

// ── Tests ──

(function () {
  // 1. Button is hidden when no reasoning exists
  var msg1 = makeMessage({ withReasoning: false });
  window._updateReasoningButton(msg1.querySelector('.message-content'));
  assert(msg1.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'Button hidden when content has no details.reasoning');

  // 2. Button is shown when reasoning exists
  var msg2 = makeMessage({ withReasoning: true });
  window._updateReasoningButton(msg2.querySelector('.message-content'));
  assert(!msg2.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'Button shown when content has details.reasoning');

  // 3. syncReasoningButtons toggles every message
  var m1 = makeMessage({ withReasoning: false });
  var m2 = makeMessage({ withReasoning: true });
  var container = makeElement('div');
  container.appendChild(m1);
  container.appendChild(m2);
  window.syncReasoningButtons(container);
  assert(m1.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'syncReasoningButtons: hides button on message without reasoning');
  assert(!m2.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'syncReasoningButtons: shows button on message with reasoning');

  // 4. syncReasoningButtons called with null is a no-op
  window.syncReasoningButtons(null);
  assert(true, 'syncReasoningButtons(null) is a safe no-op');

  // 5. preserveOpenStates — no open states
  (function () {
    var container2 = makeElement('div');
    var msg = makeMessage({ withReasoning: true });
    container2.appendChild(msg);
    var called = false;
    window.preserveOpenStates(container2, function () {
      called = true;
      return '<div class="message"><div class="message-content"></div></div>';
    });
    assert(called, 'preserveOpenStates calls renderFn');
  })();

  // 6. preserveOpenStates — with open state preserved
  (function () {
    var container3 = makeElement('div');
    var msg = makeMessage({ withReasoning: true });
    var details = msg.querySelector('details.reasoning');
    details.setAttribute('open', '');
    details.dataset.thinkId = 'think-0';
    container3.appendChild(msg);

    window.preserveOpenStates(container3, function () {
      return '<div class="message"><div class="message-content"><details class="reasoning" data-think-id="think-0">content</details></div></div>';
    });

    var restoredDetails = container3.querySelector('details.reasoning');
    assert(restoredDetails && restoredDetails.hasAttribute('open'),
      'preserveOpenStates: restores open attribute on matching thinkId');
  })();
})();

// ── Result ──
h.printSummary();
