// tests/frontend/test_abort_cleanup.js
// Unit tests for the stream abort cleanup behavior.
// The bug: when the user hits the stop button before any tokens are received,
// the asstDiv (with the spinner) was left in the DOM, forcing a page refresh.
// The fix: the AbortError catch branch must remove the empty asstDiv (for
// new messages) or refresh the message list (for regenerate).

var failures = 0, tests = 0;
function assert(cond, msg) { tests++; if (!cond) { console.error('FAIL: ' + msg); failures++; } else console.log('OK:   ' + msg); }
function assertEqual(a, b, msg) {
  tests++;
  if (a !== b) { console.error('FAIL: ' + msg + ' — expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); failures++; }
  else console.log('OK:   ' + msg);
}

// ── Minimal DOM mock (just enough for the abort logic) ──
function makeEl(tag) {
  var el = {
    tagName: tag.toUpperCase(),
    children: [],
    classList: {
      _set: new Set(),
      add(c) { this._set.add(c); },
      remove(c) { this._set.delete(c); },
      contains(c) { return this._set.has(c); },
      toggle(c, force) {
        if (force === true) this._set.add(c);
        else if (force === false) this._set.delete(c);
        else if (this._set.has(c)) this._set.delete(c);
        else this._set.add(c);
      },
    },
    parent: null,
    appendChild(c) { this.children.push(c); c.parent = this; return c; },
    remove() { if (this.parent) { var i = this.parent.children.indexOf(this); if (i >= 0) this.parent.children.splice(i, 1); this.parent = null; } },
    querySelector(sel) { return querySelectorAll(this, sel)[0] || null; },
    querySelectorAll(sel) { return querySelectorAll(this, sel); },
  };
  Object.defineProperty(el, 'parentNode', {
    get() { return el.parent; },
  });
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._innerHTML || ''; },
    set(v) {
      el._innerHTML = v;
      el.children = [];
      var m = /<(\w+)([^>]*)>/.exec(v);
      if (m) {
        var child = makeEl(m[1]);
        var cls = /class\s*=\s*"([^"]+)"/.exec(m[2]);
        if (cls) cls[1].split(/\s+/).forEach(function (c) { child.classList.add(c); });
        el.appendChild(child);
      }
    },
  });
  return el;
}

function matches(el, sel) {
  if (sel === '.message') return el.classList && el.classList.contains('message');
  if (sel === '.message-content') return el.classList && el.classList.contains('message-content');
  if (sel === '.reasoning-toggle-btn') return el.classList && el.classList.contains('reasoning-toggle-btn');
  if (sel === '.message-spinner') return el.classList && el.classList.contains('message-spinner');
  return false;
}

function querySelectorAll(root, sel) {
  var results = [];
  function walk(el) {
    if (matches(el, sel)) results.push(el);
    for (var i = 0; i < el.children.length; i++) walk(el.children[i]);
  }
  if (root) walk(root);
  return results;
}

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
}

// ── Test helpers ──
function makeAsstDiv() {
  var msg = makeEl('div');
  msg.classList.add('message');
  msg.id = 'streaming-message';

  var btn = makeEl('button');
  btn.classList.add('reasoning-toggle-btn');
  btn.classList.add('hidden');
  msg.appendChild(btn);

  var content = makeEl('div');
  content.classList.add('message-content');
  content.innerHTML = '<div class="message-spinner"></div>';
  msg.appendChild(content);

  return msg;
}

function makeExistingMessageDiv() {
  var msg = makeEl('div');
  msg.classList.add('message');
  msg.id = 'message-existing-1';

  var btn = makeEl('button');
  btn.classList.add('reasoning-toggle-btn');
  msg.appendChild(btn);

  var content = makeEl('div');
  content.classList.add('message-content');
  content.innerHTML = '<p>Previous assistant content</p>';
  msg.appendChild(content);

  return msg;
}

// ── Tests ──

(function () {
  // 1. AbortError with no text and new message: asstDiv is removed
  var parent = makeEl('div');
  var asstDiv = makeAsstDiv();
  parent.appendChild(asstDiv);
  var ajaxCalls = [];
  var err = { name: 'AbortError' };
  handleAbort(err, asstDiv, '', false, ajaxCalls);
  assert(parent.children.length === 0, 'AbortError + no text + new msg: asstDiv removed from parent');
  assert(ajaxCalls.length === 0, 'AbortError + no text + new msg: no refresh fired');

  // 2. AbortError with no text and regenerate: refresh fired, asstDiv NOT removed
  var parent2 = makeEl('div');
  var asstDiv2 = makeExistingMessageDiv();
  parent2.appendChild(asstDiv2);
  var ajaxCalls2 = [];
  handleAbort(err, asstDiv2, '', true, ajaxCalls2);
  assert(parent2.children.length === 1, 'AbortError + no text + regen: existing asstDiv preserved');
  assert(ajaxCalls2.length === 1 && ajaxCalls2[0] === 'refresh', 'AbortError + no text + regen: refresh fired');

  // 3. AbortError with some text: asstDiv kept (no remove, no refresh)
  var parent3 = makeEl('div');
  var asstDiv3 = makeAsstDiv();
  parent3.appendChild(asstDiv3);
  var ajaxCalls3 = [];
  handleAbort(err, asstDiv3, 'partial text', false, ajaxCalls3);
  assert(parent3.children.length === 1, 'AbortError + some text: asstDiv kept (partial visible)');
  assert(ajaxCalls3.length === 0, 'AbortError + some text: no refresh fired');

  // 4. AbortError with some text + regenerate: same, asstDiv kept
  var parent4 = makeEl('div');
  var asstDiv4 = makeExistingMessageDiv();
  parent4.appendChild(asstDiv4);
  var ajaxCalls4 = [];
  handleAbort(err, asstDiv4, 'partial text', true, ajaxCalls4);
  assert(parent4.children.length === 1, 'AbortError + some text + regen: asstDiv kept');
  assert(ajaxCalls4.length === 0, 'AbortError + some text + regen: no refresh fired');

  // 5. Non-AbortError: asstDiv removed, refresh fired (existing behavior)
  var parent5 = makeEl('div');
  var asstDiv5 = makeAsstDiv();
  parent5.appendChild(asstDiv5);
  var ajaxCalls5 = [];
  var realErr = { name: 'TypeError', message: 'boom' };
  handleAbort(realErr, asstDiv5, 'partial', false, ajaxCalls5);
  assert(parent5.children.length === 0, 'Non-AbortError: asstDiv removed');
  assert(ajaxCalls5.length === 1, 'Non-AbortError: refresh fired');

  // 6. Non-AbortError with regenerate: asstDiv removed, refresh fired
  var parent6 = makeEl('div');
  var asstDiv6 = makeExistingMessageDiv();
  parent6.appendChild(asstDiv6);
  var ajaxCalls6 = [];
  handleAbort(realErr, asstDiv6, '', true, ajaxCalls6);
  assert(parent6.children.length === 0, 'Non-AbortError + regen: asstDiv removed');
  assert(ajaxCalls6.length === 1, 'Non-AbortError + regen: refresh fired');
})();

// ── Result ──
console.log('\n' + tests + ' tests, ' + failures + ' failures');
process.exit(failures > 0 ? 1 : 0);
