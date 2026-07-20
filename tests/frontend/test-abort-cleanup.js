// Unit tests for the stream abort cleanup behavior (contract test).
//
// With the fully server-driven cancel architecture, the stop button sends
// a POST to /api/stop-generation/{message_id}.  The server drains gracefully
// and sends a normal ``done`` SSE event, so the error handler is only
// exercised on real connection failures (network error, server crash,
// or stop before the ``start`` event arrived).
//
// The new contract:
//   Any error → asstDiv removed + refresh fired
//   Non-AbortError also shows error toast

var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement, querySelectorAll = h.querySelectorAll;

// ── Replicate the production abort-handling logic ──
function handleAbort(err, asstDiv, htmxAjaxCalls, showToast) {
  if (err.name !== 'AbortError') {
    showToast(err.message);
  }
  if (asstDiv && asstDiv.parentNode) asstDiv.remove();
  htmxAjaxCalls.push('refresh');
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
  function noop() {}

  // 1. AbortError: asstDiv removed, refresh fired (no toast)
  var parent1 = makeElement('div');
  var asstDiv1 = makeAsstDiv();
  parent1.appendChild(asstDiv1);
  var ajaxCalls1 = [];
  handleAbort({ name: 'AbortError' }, asstDiv1, ajaxCalls1, noop);
  assert(parent1.children.length === 0, 'AbortError: asstDiv removed from parent');
  assert(ajaxCalls1.length === 1 && ajaxCalls1[0] === 'refresh', 'AbortError: refresh fired');

  // 2. AbortError with existing message div: same behavior (removed + refresh)
  var parent2 = makeElement('div');
  var asstDiv2 = makeExistingMessageDiv();
  parent2.appendChild(asstDiv2);
  var ajaxCalls2 = [];
  handleAbort({ name: 'AbortError' }, asstDiv2, ajaxCalls2, noop);
  assert(parent2.children.length === 0, 'AbortError + existing: asstDiv removed');
  assert(ajaxCalls2.length === 1, 'AbortError + existing: refresh fired');

  // 3. Non-AbortError: asstDiv removed, refresh fired, toast shown
  var parent3 = makeElement('div');
  var asstDiv3 = makeAsstDiv();
  parent3.appendChild(asstDiv3);
  var ajaxCalls3 = [];
  var toastMessages = [];
  handleAbort({ name: 'TypeError', message: 'boom' }, asstDiv3, ajaxCalls3, function (msg) { toastMessages.push(msg); });
  assert(parent3.children.length === 0, 'Non-AbortError: asstDiv removed');
  assert(ajaxCalls3.length === 1, 'Non-AbortError: refresh fired');
  assert(toastMessages.length === 1, 'Non-AbortError: toast shown');

  // 4. null/undefined asstDiv — no crash, refresh still fired
  var ajaxCalls4 = [];
  handleAbort({ name: 'AbortError' }, null, ajaxCalls4, noop);
  assert(ajaxCalls4.length === 1, 'null asstDiv: refresh still fired');
})();

// ── Result ──
h.printSummary();
