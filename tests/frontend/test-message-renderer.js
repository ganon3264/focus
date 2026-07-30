// Unit tests for message-renderer.js — rendering pipeline
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var assertIncludes = h.assertIncludes, assertNotIncludes = h.assertNotIncludes;

var path = require('path');
var fs = require('fs');

// Browser mocks
var doc = h.createMockDocument();
// Override createElement for escapeHtml: it expects textContent setter to auto-escape
doc.createElement = function () {
  var el = h.makeElement('div');
  Object.defineProperty(el, 'textContent', {
    configurable: true,
    set: function (v) {
      el._textContent = v;
      el._innerHTML = String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    },
    get: function () { return el._textContent || ''; },
  });
  return el;
};
global.document = doc;
global.window = global;
global.navigator = { clipboard: { writeText: function () {} } };

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
global.marked = { parse: mockMarkedParse, use: function () {} };
global.DOMPurify = { sanitize: function (h) { return h; } };
global.getSvgSprite = function (name, size) { return '<svg>' + name + '</svg>'; };

// Mock remend — identity function; remend's correctness is tested by its own suite
global.remend = function (t) { return t; };

// Load module
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'message-renderer.js'), 'utf8'));

// ── escapeHtml ──
(function () {
  assertEqual(window.escapeHtml('<script>alert("xss")</script>'), '&lt;script&gt;alert(&quot;xss&quot;)&lt;/script&gt;', 'escapeHtml escapes tags and quotes');
  assertEqual(window.escapeHtml('plain text'), 'plain text', 'escapeHtml leaves plain text');
  assertEqual(window.escapeHtml(''), '', 'escapeHtml handles empty string');
  assertEqual(window.escapeHtml('a & b'), 'a &amp; b', 'escapeHtml escapes ampersands');
})();

// ── extractThoughtsSafely — no thoughts ──
(function () {
  var result = window.extractThoughtsSafely('Hello world');
  assertEqual(result.processed, 'Hello world', 'extractThoughts: plain text unchanged');
  assertEqual(result.thoughts.length, 0, 'extractThoughts: no thoughts extracted');
})();

// ── extractThoughtsSafely — thought_signature removal ──
(function () {
  var result = window.extractThoughtsSafely('hello <thought_signature>sig</thought_signature> world');
  assertNotIncludes(result.processed, 'sig', 'extractThoughts: thought_signature removed');
  assertNotIncludes(result.processed, '<thought_signature>', 'extractThoughts: thought_signature tag removed');
})();

// ── renderMessage — empty input ──
(function () {
  assertEqual(window.renderMessage(''), '', 'renderMessage: empty returns empty');
  assertEqual(window.renderMessage(null), '', 'renderMessage: null returns empty');
  assertEqual(window.renderMessage(undefined), '', 'renderMessage: undefined returns empty');
})();


// ── renderMessage — code block gets copy button ──
(function () {
  var html = window.renderMessage('```\ncode\n```');
  assertIncludes(html, 'copy-btn', 'renderMessage: code block gets copy-btn');
  assertIncludes(html, 'code', 'renderMessage: code content preserved');
})();

// ── renderMessage — markdown rendered ──
(function () {
  var html = window.renderMessage('**bold**');
  assertIncludes(html, '<strong>', 'renderMessage: markdown bold rendered (or fallback)');
})();

// ── closeMarkdown — delegates to remend ──
(function () {
  assertEqual(window.closeMarkdown('hello'), 'hello', 'closeMarkdown: passes through to remend');
  assertEqual(window.closeMarkdown(''), '', 'closeMarkdown: empty returns empty');
})();

// ── Result ──
h.printSummary();
