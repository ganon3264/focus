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

// ── closeMarkdown — no-op for plain text ──
(function () {
  assertEqual(window.closeMarkdown(''), '', 'closeMarkdown: empty string');
  assertEqual(window.closeMarkdown('hello world'), 'hello world', 'closeMarkdown: plain text unchanged');
  assertEqual(window.closeMarkdown('Normal text with nothing open'), 'Normal text with nothing open', 'closeMarkdown: normal text');
})();

// ── closeMarkdown — unclosed code fence ──
(function () {
  assertEqual(window.closeMarkdown('```python\nprint("hi")'), '```python\nprint("hi")\n```', 'closeMarkdown: unclosed code fence gets closing fence');
  assertEqual(window.closeMarkdown('```\ncode\n```'), '```\ncode\n```', 'closeMarkdown: already closed fence unchanged');
})();

// ── closeMarkdown — unclosed inline code ──
(function () {
  assertEqual(window.closeMarkdown('text `code'), 'text `code`', 'closeMarkdown: unclosed inline code gets closing backtick');
})();

// ── closeMarkdown — unclosed bold/italic ──
(function () {
  assertEqual(window.closeMarkdown('**bold text'), '**bold text**', 'closeMarkdown: unclosed bold');
  assertEqual(window.closeMarkdown('*italic text'), '*italic text*', 'closeMarkdown: unclosed italic');
})();

// ── closeMarkdown — markdown inside code fence is ignored ──
(function () {
  assertEqual(window.closeMarkdown('```\n**not bold**\n```'), '```\n**not bold**\n```', 'closeMarkdown: bold inside fence not tracked');
})();

// ── closeMarkdown — constructs inside inline code are ignored ──
(function () {
  assertEqual(window.closeMarkdown('`code **not bold**`'), '`code **not bold**`', 'closeMarkdown: bold inside inline code ignored');
})();

// ── closeMarkdown — multiple unclosed constructs ──
(function () {
  var result = window.closeMarkdown('**bold and `code');
  assert(result.indexOf('`') > 0, 'closeMarkdown: multiple unclosed — backtick added');
  assert(result.lastIndexOf('**') > result.lastIndexOf('`'), 'closeMarkdown: multiple unclosed — bold added after backtick (LIFO)');
})();

// ── closeMarkdown — escaped chars skip markdown detection ──
(function () {
  assertEqual(window.closeMarkdown('\\*not italic\\*'), '\\*not italic\\*', 'closeMarkdown: escaped asterisks not tracked');
  assertEqual(window.closeMarkdown('\\`not code\\`'), '\\`not code\\`', 'closeMarkdown: escaped backtick not tracked');
})();

// ── closeMarkdown — *** bold+italic ──
(function () {
  var result = window.closeMarkdown('***everything');
  assertEqual(result, '***everything***', 'closeMarkdown: *** unclosed bold+italic');
})();

// ── closeMarkdown — fence then inline code after fence closed ──
(function () {
  var result = window.closeMarkdown('```\ncode\n``` `unclosed');
  assertEqual(result, '```\ncode\n``` `unclosed`', 'closeMarkdown: inline code after closed fence');
})();

// ── Result ──
h.printSummary();
