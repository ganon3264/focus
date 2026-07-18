// tests/frontend/test_reasoning_visibility.js
// Unit tests for the reasoning button visibility logic.
// We replicate the toggle logic from static/chat_stream.js to verify the
// expected behavior, since the production function lives inside an IIFE
// with many DOM dependencies. The contract being tested:
//   - Button is hidden when the message content has no `details.reasoning`
//   - Button is shown when the message content has a `details.reasoning`
//   - `syncReasoningButtons(container)` toggles every message in container
//   - After a regen-start (spinner inserted), the button must be hidden
//     regardless of what was there before.

var failures = 0, tests = 0;
function assert(cond, msg) { tests++; if (!cond) { console.error('FAIL: ' + msg); failures++; } else console.log('OK:   ' + msg); }
function assertEqual(a, b, msg) {
  tests++;
  if (a !== b) { console.error('FAIL: ' + msg + ' — expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); failures++; }
  else console.log('OK:   ' + msg);
}

// ── Minimal DOM mock (just enough for the toggle logic) ──
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
    _attrs: {},
    setAttribute(k, v) { this._attrs[k] = v; },
    getAttribute(k) { return this._attrs[k]; },
    hasAttribute(k) { return k in this._attrs; },
    removeAttribute(k) { delete this._attrs[k]; },
    appendChild(c) { this.children.push(c); c.parent = this; return c; },
    querySelector(sel) { return querySelectorAll(this, sel)[0] || null; },
    querySelectorAll(sel) { return querySelectorAll(this, sel); },
    closest(sel) {
      var n = this;
      while (n) {
        if (n === this && matches(n, sel)) return n;
        if (n.parent && matches(n.parent, sel)) return n.parent;
        n = n.parent;
      }
      return null;
    },
    dataset: {},
  };
  Object.defineProperty(el, 'innerHTML', {
    get() { return el._innerHTML || ''; },
    set(v) {
      el._innerHTML = v;
      el.children = [];
      // Very small HTML parser for our test scenarios: a single <tag class="...">
      var m = /<(\w+)([^>]*)>/.exec(v);
      if (m) {
        var child = makeEl(m[1]);
        var cls = /class\s*=\s*"([^"]+)"/.exec(m[2]);
        if (cls) cls[1].split(/\s+/).forEach(function (c) { child.classList.add(c); });
        el.appendChild(child);
      }
    },
  });
  Object.defineProperty(el, 'textContent', {
    get() { return el._textContent || ''; },
    set(v) { el._textContent = v; el.children = []; },
  });
  return el;
}

function matches(el, sel) {
  if (sel.startsWith('.')) return el.classList && el.classList.contains(sel.slice(1));
  if (sel.startsWith('details.reasoning')) return el.tagName === 'DETAILS' && el.classList.contains('reasoning');
  if (sel === 'details.reasoning') return el.tagName === 'DETAILS' && el.classList.contains('reasoning');
  if (sel.startsWith('details')) return el.tagName === sel.toUpperCase();
  return false;
}

function querySelectorAll(root, sel) {
  var results = [];
  function walk(el) {
    if (matches(el, sel)) results.push(el);
    for (var i = 0; i < el.children.length; i++) walk(el.children[i]);
  }
  if (root.tagName || root === document) walk(root);
  return results;
}

// Mock document
global.document = {
  _root: makeEl('body'),
  querySelector(sel) { return this._root.querySelector(sel); },
  querySelectorAll(sel) { return this._root.querySelectorAll(sel); },
};
// Make document itself walkable
document._root.tagName = 'BODY';

// ── Replicate the production toggle logic ──
function _updateReasoningButton(contentDiv) {
  var msg = contentDiv.closest('.message');
  if (!msg) return;
  var btn = msg.querySelector('.reasoning-toggle-btn');
  if (!btn) return;
  var hasReasoning = !!contentDiv.querySelector('details.reasoning');
  btn.classList.toggle('hidden', !hasReasoning);
}

function syncReasoningButtons(container) {
  if (!container) return;
  var root = container === document ? document : container;
  root.querySelectorAll('.message-content').forEach(function (el) {
    _updateReasoningButton(el);
  });
}

// Replicate the regen-start hide behavior
function regenStart(asstDiv) {
  var contentDiv = asstDiv.querySelector('.message-content');
  if (contentDiv) {
    contentDiv.innerHTML = '<div class="message-spinner"></div>';
  }
  var reasoningBtn = asstDiv.querySelector('.reasoning-toggle-btn');
  if (reasoningBtn) reasoningBtn.classList.add('hidden');
}

// ── Test helpers ──
function makeMessage(opts) {
  opts = opts || {};
  var msg = makeEl('div');
  msg.classList.add('message');

  var btn = makeEl('button');
  btn.classList.add('reasoning-toggle-btn');
  if (opts.buttonHiddenInitially) btn.classList.add('hidden');
  msg.appendChild(btn);

  var content = makeEl('div');
  content.classList.add('message-content');
  if (opts.withReasoning) {
    var details = makeEl('details');
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
  _updateReasoningButton(msg1.querySelector('.message-content'));
  assert(msg1.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'Button hidden when content has no details.reasoning');

  // 2. Button is shown when reasoning exists
  var msg2 = makeMessage({ withReasoning: true });
  _updateReasoningButton(msg2.querySelector('.message-content'));
  assert(!msg2.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'Button shown when content has details.reasoning');

  // 3. syncReasoningButtons toggles every message
  var m1 = makeMessage({ withReasoning: false });
  var m2 = makeMessage({ withReasoning: true });
  var root = makeEl('div');
  root.appendChild(m1);
  root.appendChild(m2);
  syncReasoningButtons(root);
  assert(m1.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'syncReasoningButtons: hides button on message without reasoning');
  assert(!m2.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'syncReasoningButtons: shows button on message with reasoning');

  // 4. regenStart hides a previously-visible button (THE BUG FIX)
  var msg3 = makeMessage({ withReasoning: true });
  assert(!msg3.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'Pre-condition: button visible before regen');
  regenStart(msg3);
  assert(msg3.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'regenStart hides the button even when reasoning was previously visible');

  // 5. After regenStart, syncReasoningButtons keeps button hidden (no reasoning in spinner)
  var msg4 = makeMessage({ withReasoning: true });
  regenStart(msg4);
  syncReasoningButtons(msg4);
  assert(msg4.querySelector('.reasoning-toggle-btn').classList.contains('hidden'),
    'syncReasoningButtons after regenStart: button stays hidden (no reasoning in spinner)');

  // 6. syncReasoningButtons called with null is a no-op
  syncReasoningButtons(null);
  assert(true, 'syncReasoningButtons(null) is a safe no-op');
})();

// ── Result ──
console.log('\n' + tests + ' tests, ' + failures + ' failures');
process.exit(failures > 0 ? 1 : 0);
