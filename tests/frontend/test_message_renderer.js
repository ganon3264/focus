// Unit tests for message_renderer.js — rendering pipeline
var h = require('./_helpers.js');
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
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'message_renderer.js'), 'utf8'));

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

// ── extractThoughtsSafely — think block ──
(function () {
  var result = window.extractThoughtsSafely('before<think>hidden</think>after');
  assertEqual(result.thoughts.length, 1, 'extractThoughts: one thought');
  assertEqual(result.thoughts[0].content, 'hidden', 'extractThoughts: thought content');
  assertNotIncludes(result.processed, 'hidden', 'extractThoughts: thought content removed from processed');
  assertIncludes(result.processed, '%%%THINK_BLOCK_0%%%', 'extractThoughts: placeholder inserted');
})();

// ── extractThoughtsSafely — unclosed think block ──
(function () {
  var result = window.extractThoughtsSafely('<think>unclosed');
  assert(result.thoughts.length === 1, 'extractThoughts: unclosed thought extracted');
  assertEqual(result.thoughts[0].content, 'unclosed', 'extractThoughts: unclosed content');
})();

// ── extractThoughtsSafely — code blocks protect think tags ──
(function () {
  var result = window.extractThoughtsSafely('```\n<think>inside code</think>\n```');
  assertEqual(result.thoughts.length, 0, 'extractThoughts: think inside code block ignored');
  assert(result.processed.indexOf('<think>') >= 0, 'extractThoughts: code block content preserved');
})();

// ── extractThoughtsSafely — thought_signature removal ──
(function () {
  var result = window.extractThoughtsSafely('hello <thought_signature>sig</thought_signature> world');
  assertNotIncludes(result.processed, 'sig', 'extractThoughts: thought_signature removed');
  assertNotIncludes(result.processed, '<thought_signature>', 'extractThoughts: thought_signature tag removed');
})();

// ── extractThoughtsSafely — inline code protected ──
(function () {
  var result = window.extractThoughtsSafely('`<think>inline</think>`');
  assertEqual(result.thoughts.length, 0, 'extractThoughts: think inside inline code ignored');
})();

// ── extractThoughtsSafely — multiple think blocks ──
(function () {
  var result = window.extractThoughtsSafely('a<think>first</think>b<think>second</think>c');
  assertEqual(result.thoughts.length, 2, 'extractThoughts: two thoughts');
  assertEqual(result.thoughts[0].content, 'first', 'extractThoughts: first thought content');
  assertEqual(result.thoughts[1].content, 'second', 'extractThoughts: second thought content');
})();

// ── renderMessage — empty input ──
(function () {
  assertEqual(window.renderMessage(''), '', 'renderMessage: empty returns empty');
  assertEqual(window.renderMessage(null), '', 'renderMessage: null returns empty');
  assertEqual(window.renderMessage(undefined), '', 'renderMessage: undefined returns empty');
})();

// ── renderMessage — think block produces .reasoning-block ──
(function () {
  var html = window.renderMessage('hello<think>hidden</think>world');
  assertIncludes(html, 'class="reasoning-block"', 'renderMessage: think becomes reasoning-block');
  assertNotIncludes(html, 'class="details reasoning-block"', 'renderMessage: single block is not details');
  assertNotIncludes(html, '<summary>', 'renderMessage: single block has no summary');
  assertIncludes(html, 'hidden', 'renderMessage: think content in output');
  assertIncludes(html, 'hello', 'renderMessage: text before think preserved');
  assertIncludes(html, 'world', 'renderMessage: text after think preserved');

  var html2 = window.renderMessage('a<think>first</think>b<think>second</think>c');
  assertIncludes(html2, '<summary>', 'renderMessage: second block has summary');
  var summaries = (html2.match(/<summary>/g) || []).length;
  assertEqual(summaries, 1, 'renderMessage: only one summary (second block)');
  assertEqual(
    (html2.match(/class="details reasoning-block"/g) || []).length, 1,
    'renderMessage: only second block uses details'
  );
  assertEqual(
    (html2.match(/reasoning-block/g) || []).length, 2,
    'renderMessage: both blocks have reasoning-block class'
  );
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

// ── renderMessage — think inside code block not rendered as reasoning ──
(function () {
  var html = window.renderMessage('```\n<think>not a real thought</think>\n```');
  assertNotIncludes(html, 'details class="reasoning"', 'renderMessage: think inside code not rendered as reasoning');
  assertNotIncludes(html, '%%%THINK_BLOCK', 'renderMessage: no unresolved think placeholders');
  assertIncludes(html, '<pre>', 'renderMessage: code block preserved as pre');
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
