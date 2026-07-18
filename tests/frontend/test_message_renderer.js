// Unit tests for message_renderer.js — rendering pipeline
var failures = 0, tests = 0;

function assert(cond, msg) { tests++; if (!cond) { console.error('FAIL: ' + msg); failures++; } else console.log('OK:   ' + msg); }
function assertEqual(a, b, msg) { tests++; if (a !== b) { console.error('FAIL: ' + msg + ' — expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); failures++; } else console.log('OK:   ' + msg); }
function assertIncludes(haystack, needle, msg) { tests++; if (haystack.indexOf(needle) === -1) { console.error('FAIL: ' + msg + ' — expected "' + needle + '" not found in output'); failures++; } else console.log('OK:   ' + msg); }
function assertNotIncludes(haystack, needle, msg) { tests++; if (haystack.indexOf(needle) !== -1) { console.error('FAIL: ' + msg + ' — unexpected "' + needle + '" found in output'); failures++; } else console.log('OK:   ' + msg); }

var path = require('path');
var fs = require('fs');

// Mock document for escapeHtml + event listener (click on .copy-btn)
global.document = {
  createElement: function() {
    var el = { textContent: '', innerHTML: '' };
    Object.defineProperty(el, 'textContent', {
      set: function(v) { el.innerHTML = String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); },
      get: function() { return el.innerHTML.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"'); }
    });
    return el;
  },
  addEventListener: function() {}
};
global.navigator = { clipboard: { writeText: function() {} } };
global.window = global;

// Simulate marked parse for common patterns
function mockMarkedParse(text) {
  if (!text) return '';
  var r = text;
  r = r.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  r = r.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  r = r.replace(/`([^`]+)`/g, '<code>$1</code>');
  if (!r.startsWith('<')) r = '<p>' + r + '</p>';
  return r;
}
global.marked = { parse: mockMarkedParse, use: function() {} };
// Mock DOMPurify
global.DOMPurify = { sanitize: function(h) { return h; } };
// Mock getSvgSprite
global.getSvgSprite = function(name, size) { return '<svg>' + name + '</svg>'; };

// Load module
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'message_renderer.js'), 'utf8'));

// ── escapeHtml ──
(function() {
  assertEqual(window.escapeHtml('<script>alert("xss")</script>'), '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;', 'escapeHtml escapes tags and quotes');
  assertEqual(window.escapeHtml('plain text'), 'plain text', 'escapeHtml leaves plain text');
  assertEqual(window.escapeHtml(''), '', 'escapeHtml handles empty string');
  assertEqual(window.escapeHtml('a & b'), 'a &amp; b', 'escapeHtml escapes ampersands');
})();

// ── extractThoughtsSafely — no thoughts ──
(function() {
  var result = window.extractThoughtsSafely('Hello world');
  assertEqual(result.processed, 'Hello world', 'extractThoughts: plain text unchanged');
  assertEqual(result.thoughts.length, 0, 'extractThoughts: no thoughts extracted');
})();

// ── extractThoughtsSafely — think block ──
(function() {
  var result = window.extractThoughtsSafely('before<think>hidden</think>after');
  assertEqual(result.thoughts.length, 1, 'extractThoughts: one thought');
  assertEqual(result.thoughts[0].content, 'hidden', 'extractThoughts: thought content');
  assert(result.thoughts[0].isClosed, 'extractThoughts: thought is closed');
  assertNotIncludes(result.processed, 'hidden', 'extractThoughts: thought content removed from processed');
  assertIncludes(result.processed, '%%%THINK_BLOCK_0%%%', 'extractThoughts: placeholder inserted');
})();

// ── extractThoughtsSafely — unclosed think block ──
(function() {
  var result = window.extractThoughtsSafely('<think>unclosed');
  assert(result.thoughts.length === 1, 'extractThoughts: unclosed thought extracted');
  assert(!result.thoughts[0].isClosed, 'extractThoughts: unclosed flagged');
  assertEqual(result.thoughts[0].content, 'unclosed', 'extractThoughts: unclosed content');
})();

// ── extractThoughtsSafely — code blocks protect think tags ──
(function() {
  var result = window.extractThoughtsSafely('```\n<think>inside code</think>\n```');
  assertEqual(result.thoughts.length, 0, 'extractThoughts: think inside code block ignored');
  assertEqual(result.processed.indexOf('<think>') >= 0, true, 'extractThoughts: code block content preserved');
})();

// ── extractThoughtsSafely — thought_signature removal ──
(function() {
  var result = window.extractThoughtsSafely('hello <thought_signature>sig</thought_signature> world');
  assertNotIncludes(result.processed, 'sig', 'extractThoughts: thought_signature removed');
  assertNotIncludes(result.processed, '<thought_signature>', 'extractThoughts: thought_signature tag removed');
})();

// ── extractThoughtsSafely — inline code protected ──
(function() {
  var result = window.extractThoughtsSafely('`<think>inline</think>`');
  assertEqual(result.thoughts.length, 0, 'extractThoughts: think inside inline code ignored');
})();

// ── extractThoughtsSafely — multiple think blocks ──
(function() {
  var result = window.extractThoughtsSafely('a<think>first</think>b<think>second</think>c');
  assertEqual(result.thoughts.length, 2, 'extractThoughts: two thoughts');
  assertEqual(result.thoughts[0].content, 'first', 'extractThoughts: first thought content');
  assertEqual(result.thoughts[1].content, 'second', 'extractThoughts: second thought content');
})();

// ── renderMessage — empty input ──
(function() {
  assertEqual(window.renderMessage(''), '', 'renderMessage: empty returns empty');
  assertEqual(window.renderMessage(null), '', 'renderMessage: null returns empty');
  assertEqual(window.renderMessage(undefined), '', 'renderMessage: undefined returns empty');
})();

// ── renderMessage — think block produces details.reasoning ──
(function() {
  var html = window.renderMessage('hello<think>hidden</think>world');
  assertIncludes(html, '<details class="reasoning"', 'renderMessage: think becomes details.reasoning');
  assertIncludes(html, '<summary>', 'renderMessage: details has summary');
  assertIncludes(html, 'hidden', 'renderMessage: think content in output');
  assertIncludes(html, 'hello', 'renderMessage: text before think preserved');
  assertIncludes(html, 'world', 'renderMessage: text after think preserved');
})();

// ── renderMessage — code block gets copy button ──
(function() {
  var html = window.renderMessage('```\ncode\n```');
  assertIncludes(html, 'copy-btn', 'renderMessage: code block gets copy-btn');
  assertIncludes(html, 'code', 'renderMessage: code content preserved');
})();

// ── renderMessage — markdown rendered ──
(function() {
  var html = window.renderMessage('**bold**');
  assertIncludes(html, '<strong>', 'renderMessage: markdown bold rendered (or fallback)');
})();

// ── renderMessage — think inside code block not rendered as reasoning ──
(function() {
  var html = window.renderMessage('```\n<think>not a real thought</think>\n```');
  assertNotIncludes(html, 'details class="reasoning"', 'renderMessage: think inside code not rendered as reasoning');
  assertNotIncludes(html, '%%%THINK_BLOCK', 'renderMessage: no unresolved think placeholders');
  assertIncludes(html, '<pre>', 'renderMessage: code block preserved as pre');
})();

// ── Result ──
console.log('\n' + tests + ' tests, ' + failures + ' failures');
process.exit(failures > 0 ? 1 : 0);
