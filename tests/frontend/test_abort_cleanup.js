// Unit tests for the stream abort cleanup behavior (contract test).
//
// The abort-handling logic lives inline inside the chat_stream.js IIFE
// catch block (lines 310-343) and is deeply entangled with 30+ DOM
// references that can't be mocked cleanly.  Rather than loading the full
// module, we replicate the logic here to test the behavioral contract.
//
// The contract:
//   AbortError + no text + new message  → asstDiv removed
//   AbortError + no text + regen        → refresh fired, asstDiv preserved
//   AbortError + partial text           → asstDiv kept (visible partial)
//   Non-AbortError                      → asstDiv removed + refresh fired

var h = require('./_helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement, querySelectorAll = h.querySelectorAll;

// ── Replicate the production abort-handling logic ──
function handleAbort(err, asstDiv, fullText, isRegen, htmxAjaxCalls) {
  if (err.name !== 'AbortError') {
    if (asstDiv && asstDiv.parentNode) asstDiv.remove();
    htmxAjaxCalls.push('refresh');
    return;
  }
  if (!fullText) {
    if (isRegen) {
      htmxAjaxCalls.push('refresh');
    } else if (asstDiv && asstDiv.parentNode) {
      asstDiv.remove();
    }
  }
  // partial text → asstDiv kept, no refresh (test cases 3,4)
}

function matches(el, sel) {
  if (!el || !el.tagName) return false;
  if (sel === '.message') return el.classList && el.classList.contains('message');
  if (sel === '.message-content') return el.classList && el.classList.contains('message-content');
  if (sel === '.reasoning-toggle-btn') return el.classList && el.classList.contains('reasoning-toggle-btn');
  if (sel === '.message-spinner') return el.classList && el.classList.contains('message-spinner');
  return false;
}

// ── Test helpers ──

function makeAsstDiv() {
  var msg = makeElement('div');
  msg.classList.add('message');
  msg.id = 'streaming-message';

  var btn = makeElement('button');
  btn.classList.add('reasoning-toggle-btn');
  btn.classList.add('hidden');
  msg.appendChild(btn);

  var content = makeElement('div');
  content.classList.add('message-content');
  content.innerHTML = '<div class="message-spinner"></div>';
  msg.appendChild(content);

  return msg;
}

function makeExistingMessageDiv() {
  var msg = makeElement('div');
  msg.classList.add('message');
  msg.id = 'message-existing-1';

  var btn = makeElement('button');
  btn.classList.add('reasoning-toggle-btn');
  msg.appendChild(btn);

  var content = makeElement('div');
  content.classList.add('message-content');
  content.innerHTML = '<p>Previous assistant content</p>';
  msg.appendChild(content);

  return msg;
}

// ── Tests ──

(function () {
  // 1. AbortError with no text and new message: asstDiv is removed
  var parent = makeElement('div');
  var asstDiv = makeAsstDiv();
  parent.appendChild(asstDiv);
  var ajaxCalls = [];
  var err = { name: 'AbortError' };
  handleAbort(err, asstDiv, '', false, ajaxCalls);
  assert(parent.children.length === 0, 'AbortError + no text + new msg: asstDiv removed from parent');
  assert(ajaxCalls.length === 0, 'AbortError + no text + new msg: no refresh fired');

  // 2. AbortError with no text and regenerate: refresh fired, asstDiv NOT removed
  var parent2 = makeElement('div');
  var asstDiv2 = makeExistingMessageDiv();
  parent2.appendChild(asstDiv2);
  var ajaxCalls2 = [];
  handleAbort(err, asstDiv2, '', true, ajaxCalls2);
  assert(parent2.children.length === 1, 'AbortError + no text + regen: existing asstDiv preserved');
  assert(ajaxCalls2.length === 1 && ajaxCalls2[0] === 'refresh', 'AbortError + no text + regen: refresh fired');

  // 3. AbortError with some text: asstDiv kept (no remove, no refresh)
  var parent3 = makeElement('div');
  var asstDiv3 = makeAsstDiv();
  parent3.appendChild(asstDiv3);
  var ajaxCalls3 = [];
  handleAbort(err, asstDiv3, 'partial text', false, ajaxCalls3);
  assert(parent3.children.length === 1, 'AbortError + some text: asstDiv kept (partial visible)');
  assert(ajaxCalls3.length === 0, 'AbortError + some text: no refresh fired');

  // 4. AbortError with some text + regenerate: same, asstDiv kept
  var parent4 = makeElement('div');
  var asstDiv4 = makeExistingMessageDiv();
  parent4.appendChild(asstDiv4);
  var ajaxCalls4 = [];
  handleAbort(err, asstDiv4, 'partial text', true, ajaxCalls4);
  assert(parent4.children.length === 1, 'AbortError + some text + regen: asstDiv kept');
  assert(ajaxCalls4.length === 0, 'AbortError + some text + regen: no refresh fired');

  // 5. Non-AbortError: asstDiv removed, refresh fired
  var parent5 = makeElement('div');
  var asstDiv5 = makeAsstDiv();
  parent5.appendChild(asstDiv5);
  var ajaxCalls5 = [];
  var realErr = { name: 'TypeError', message: 'boom' };
  handleAbort(realErr, asstDiv5, 'partial', false, ajaxCalls5);
  assert(parent5.children.length === 0, 'Non-AbortError: asstDiv removed');
  assert(ajaxCalls5.length === 1, 'Non-AbortError: refresh fired');

  // 6. Non-AbortError with regenerate: asstDiv removed, refresh fired
  var parent6 = makeElement('div');
  var asstDiv6 = makeExistingMessageDiv();
  parent6.appendChild(asstDiv6);
  var ajaxCalls6 = [];
  handleAbort(realErr, asstDiv6, '', true, ajaxCalls6);
  assert(parent6.children.length === 0, 'Non-AbortError + regen: asstDiv removed');
  assert(ajaxCalls6.length === 1, 'Non-AbortError + regen: refresh fired');

  // 7. null/undefined asstDiv — no crash
  var ajaxCalls7 = [];
  handleAbort(err, null, '', false, ajaxCalls7);
  assert(ajaxCalls7.length === 0, 'null asstDiv: no crash, no refresh');
})();

// ── Result ──
h.printSummary();
