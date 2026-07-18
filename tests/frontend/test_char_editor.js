// Unit tests for char_editor.js — character card editor (Alpine component + functions)
var h = require('./_helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

// Build DOM with elements char_editor needs
var importIndicator = makeElement('div');
importIndicator.id = 'import-indicator';
importIndicator.classList.add('hidden');

var doc = h.createMockDocument();
doc._body.appendChild(importIndicator);
doc.getElementById = function (id) {
  if (id === 'import-indicator') return importIndicator;
  return null;
};
doc.body = doc._body;
doc.body.addEventListener = function () {};
doc.addEventListener = function (event, handler) {
  if (event === 'alpine:init') handler();
};
doc.createElement = function (tag) {
  var el = h.makeElement(tag);
  el.appendChild = function (c) {
    var idx = this.children.indexOf(c); if (idx >= 0) this.children.splice(idx, 1);
    this.children.push(c); c.parent = this; return c;
  };
  return el;
};

global.window = global;
global.document = doc;
global.fetch = function () { return Promise.resolve({ ok: true, json: function () { return {}; } }); };
global.alert = function () {};
global.api = {
  characters: function (id) { return '/api/characters/' + id; },
  charBlocks: function (id) { return '/api/characters/' + id + '/blocks'; },
  charBlock: function (cid, bid) { return '/api/characters/' + cid + '/blocks/' + bid; },
  charImages: function (id) { return '/api/characters/' + id + '/images'; },
  charImage: function (cid, iid) { return '/api/characters/' + cid + '/images/' + iid; },
};
global.customConfirm = function () {};
global.buildMediaThumbnail = function () { return doc.createElement('div'); };
global.handleAvatarUpload = function () {};
global.location = { search: '', href: '' };

// Mock Alpine
global.Alpine = {
  data: function (name, factory) {
    Alpine._components = Alpine._components || {};
    Alpine._components[name] = factory;
  },
  $nextTick: function (fn) { fn(); },
};
global.URLSearchParams = function (qs) {
  var p = {};
  if (qs) qs.replace('?', '').split('&').forEach(function (kv) {
    var x = kv.split('='); p[x[0]] = x[1];
  });
  return { get: function (k) { return p[k] || null; } };
};
global.ALL_CHARS = [];

// Load module
var src = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'features', 'char_editor.js'), 'utf8');
eval(src + '\nwindow.importCharPage=importCharPage;window.promptDeleteChar=promptDeleteChar;window.saveCharCard=saveCharCard;window.addGreeting=addGreeting;window.addBlock=addBlock;window.updateBlock=updateBlock;window.deleteBlock=deleteBlock;window.uploadCharMedia=uploadCharMedia;window.deleteCharMedia=deleteCharMedia;window.uploadCharBlockMedia=uploadCharBlockMedia;window.deleteCharBlockMedia=deleteCharBlockMedia;');

assert(typeof window.importCharPage === 'function', 'importCharPage loaded');
assert(typeof window.saveCharCard === 'function', 'saveCharCard loaded');
assert(typeof window.addBlock === 'function', 'addBlock loaded');

// ── Alpine charEditor component registered ──
(function () {
  assert(!!Alpine._components.charEditor, 'Alpine charEditor component registered');
})();

// ── Alpine component data ──
(function () {
  var data = Alpine._components.charEditor();
  assertEqual(data.detailId, null, 'initial detailId null');
  assert(typeof data.selectChar === 'function', 'selectChar is function');
  assert(typeof data.init === 'function', 'init is function');
  assert(Array.isArray(data.charsList), 'charsList is array');
})();

// ── selectChar updates detailId ──
(function () {
  var data = Alpine._components.charEditor();
  data.selectChar('char-123');
  assertEqual(data.detailId, 'char-123', 'selectChar sets detailId');
})();

// ── activeChar computed property ──
(function () {
  var data = Alpine._components.charEditor();
  data.charsList = [{ id: 'c1', name: 'Alice' }, { id: 'c2', name: 'Bob' }];
  data.selectChar('c2');
  assertEqual(data.activeChar.name, 'Bob', 'activeChar returns matching char');
})();

// ── activeChar returns null when no selection ──
(function () {
  var data = Alpine._components.charEditor();
  data.charsList = [{ id: 'c1', name: 'Alice' }];
  assertEqual(data.activeChar, null, 'activeChar null when no detailId');
})();

// ── init selects from URL param ──
(function () {
  global.ALL_CHARS = [{ id: 'url-char', name: 'FromURL' }];
  global.location.search = '?char=url-char';

  var data = Alpine._components.charEditor();
  data.charsList = global.ALL_CHARS;
  data.init();
  assertEqual(data.detailId, 'url-char', 'init reads char from URL param');
})();

// ── init falls back to first char when no URL param ──
(function () {
  global.ALL_CHARS = [{ id: 'first', name: 'First' }, { id: 'second', name: 'Second' }];
  global.location.search = '';

  var data = Alpine._components.charEditor();
  data.charsList = global.ALL_CHARS;
  data.init();
  assertEqual(data.detailId, 'first', 'init falls back to first char');
})();

// ── promptDeleteChar is callable ──
(function () {
  assert(typeof window.promptDeleteChar === 'function', 'promptDeleteChar is function');
})();

// ── Result ──
h.printSummary();
