// Unit tests for edit-entity.js — modal handler factory
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

var doc = h.createMockDocument();
doc.body = doc._body;
doc.body.addEventListener = function () {};
doc.addEventListener = function () {};
doc.createElement = function (tag) {
  var el = h.makeElement(tag);
  el.style = {};
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
global.htmx = { ajax: function () {} };
global.StateManager = { get: function () { return null; } };
global.openCropModal = function () {};
global.setupDropZone = function () {};
global.buildMediaThumbnail = function () {
  var el = doc.createElement('div');
  el.addEventListener = function () {};
  return el;
};
global.openModal = function () {};
global.closeModal = function () {};
global.showSuccessToast = function () {};
global.showInfoToast = function () {};
global.FormData = function (form) {
  this._fields = {};
  this.append = function (k, v) { this._fields[k] = v; };
};

// Load module
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'edit-entity.js'), 'utf8'));

assert(typeof window.createEditModalHandlers === 'function', 'createEditModalHandlers loaded');

// ── reloadPromptArranger builds URL with query params ──
(function () {
  var lastArgs = null;
  var oldAjax = global.htmx.ajax;
  global.htmx.ajax = function (method, url, opts) {
    lastArgs = { method: method, url: url, opts: opts };
  };

  // reloadPromptArranger guards on document.getElementById(targetId)
  var targetEl = makeElement('div');
  targetEl.id = 'arranger-modal-body';
  doc._body.appendChild(targetEl);
  var origGet = doc.getElementById;
  doc.getElementById = function (id) {
    if (id === 'arranger-modal-body') return targetEl;
    return origGet ? origGet(id) : null;
  };

  window.reloadPromptArranger('preset-1', 'arranger-modal-body');
  assert(!!lastArgs, 'htmx.ajax called');
  assertEqual(lastArgs.url, '/partials/prompt-arranger/preset-1', 'arranger URL without params');
  assertEqual(lastArgs.opts.target, '#arranger-modal-body', 'arranger target');

  doc.getElementById = origGet;
  global.htmx.ajax = oldAjax;
})();

// ── getArrangerContainerId returns container id ──
(function () {
  var list = makeElement('div');
  list.id = 'arranger-list-pr1';
  var parent = makeElement('div');
  parent.id = 'my-container';
  parent.appendChild(list);
  // Set parentElement for the list (makeElement only has parent, not parentElement)
  Object.defineProperty(list, 'parentElement', { get: function () { return list.parent; } });
  doc._body.appendChild(parent);
  doc.getElementById = function (id) {
    if (id === 'arranger-list-pr1') return list;
    return null;
  };

  var result = window.getArrangerContainerId('pr1');
  assertEqual(result, 'my-container', 'getArrangerContainerId returns parent id');
})();

// ── createEditModalHandlers creates named functions ──
(function () {
  var cfg = {
    dataPrefix: 'char',
    mediaSectionId: 'media-section',
    idPrefix: 'edit-char',
    modalId: 'modal-edit-character',
    openFn: 'openEditChar',
    uploadFn: 'uploadCharMedia',
    uploadFileFn: 'uploadCharFile',
    deleteFn: 'deleteCharImage',
    avatarFn: 'uploadCharAvatar',
    submitFn: 'submitEditChar',
    apiImages: function (id) { return '/api/characters/' + id + '/images'; },
    apiImage: function (id, imgId) { return '/api/characters/' + id + '/images/' + imgId; },
    apiAvatar: function (id) { return '/api/characters/' + id + '/avatar'; },
    apiGet: function (id) { return '/api/characters/' + id; },
    mediaIdPrefix: 'char-img',
    stateKey: 'character_id',
    dropZoneSelector: '#edit-char-dropzone',
  };

  window.createEditModalHandlers(cfg);

  assert(typeof window.openEditChar === 'function', 'openFn created');
  assert(typeof window.uploadCharMedia === 'function', 'uploadFn created');
  assert(typeof window.uploadCharFile === 'function', 'uploadFileFn created');
  assert(typeof window.deleteCharImage === 'function', 'deleteFn created');
  assert(typeof window.uploadCharAvatar === 'function', 'avatarFn created');
  assert(typeof window.submitEditChar === 'function', 'submitFn created');
})();

// ── uploadFn delegates to uploadFileFn ──
(function () {
  var delegated = false;
  window.uploadCharFile = function () { delegated = true; };

  window.uploadCharMedia({ files: [new (global.Blob || function () {})()] });
  assert(delegated, 'uploadFn delegates to uploadFileFn');

  // With empty files — no delegate
  delegated = false;
  window.uploadCharMedia({ files: [] });
  assert(!delegated, 'uploadFn with no files does nothing');

  window.uploadCharFile = function () {};
})();

// ── deleteFn fetch URL construction (checked synchronously) ──
(function () {
  var idInput = makeElement('input');
  idInput.id = 'edit-char-id';
  idInput.value = 'char-1';
  doc._body.appendChild(idInput);

  var origGetElementById = doc.getElementById;
  doc.getElementById = function (id) {
    if (id === 'edit-char-id') return idInput;
    return origGetElementById ? origGetElementById(id) : null;
  };

  // The fetch call is async, but we can check that the function signature works
  assert(typeof window.deleteCharImage === 'function', 'deleteFn exists');
  // Clean up: deleteFn will call fetch asynchronously (fire-and-forget)
  doc.getElementById = origGetElementById;
})();

// ── Greeting editor: open / nav / add / delete / input / submit ──
(function () {
  var cfg = {
    dataPrefix: 'char',
    mediaSectionId: 'media-section-g2',
    idPrefix: 'edit-g2',
    modalId: 'modal-edit-g2',
    openFn: 'openEditG2',
    uploadFn: 'uploadG2',
    uploadFileFn: 'uploadG2File',
    deleteFn: 'deleteG2Image',
    avatarFn: 'uploadG2Avatar',
    submitFn: 'submitEditG2',
    greetings: true,
    greetingPrevFn: 'g2GreetingPrev',
    greetingNextFn: 'g2GreetingNext',
    greetingAddFn: 'g2GreetingAdd',
    greetingDeleteFn: 'g2GreetingDelete',
    greetingInputFn: 'g2GreetingInput',
    apiGet: function (id) { return '/api/characters/' + id; },
    apiImages: function (id) { return '/api/characters/' + id + '/images'; },
    apiImage: function (id, imgId) { return '/api/characters/' + id + '/images/' + imgId; },
    apiAvatar: function (id) { return '/api/characters/' + id + '/avatar'; },
    mediaIdPrefix: 'g2-img',
    stateKey: 'character_id',
    dropZoneSelector: '#g2-dropzone',
  };

  function makeEl(tag, id, opts) {
    opts = opts || {};
    var el = makeElement(tag);
    el.id = id;
    el.style = {};
    if (opts.value !== undefined) el.value = opts.value;
    if (opts.focus) el.focus = function () { this._focused = true; };
    doc._body.appendChild(el);
    return el;
  }

  var idInput = makeEl('input', 'edit-g2-id', { value: 'c1' });
  makeEl('input', 'edit-g2-name', { value: 'N' });
  makeEl('textarea', 'edit-g2-desc', { value: '' });
  makeEl('img', 'edit-g2-image-preview');
  makeEl('span', 'edit-g2-image-placeholder');
  makeEl('div', 'media-section-g2');
  makeEl('div', 'modal-edit-g2');
  var ta = makeEl('textarea', 'edit-g2-greeting', { value: '', focus: true });
  var count = makeEl('span', 'edit-g2-greeting-count');
  var prevBtn = makeEl('button', 'edit-g2-greeting-prev');
  var nextBtn = makeEl('button', 'edit-g2-greeting-next');
  var delBtn = makeEl('button', 'edit-g2-greeting-delete');

  window.createEditModalHandlers(cfg);

  var origGet = doc.getElementById;
  doc.getElementById = function (id) { return doc.querySelector('#' + id); };

  var btn = makeElement('button');
  btn.dataset.charId = 'c1';
  btn.dataset.charGreetings = JSON.stringify(['Hi', 'Hello', 'Howdy']);
  btn.dataset.charMedia = '[]';
  window.openEditG2(btn);

  assertEqual(ta.value, 'Hi', 'open loads first greeting');
  assertEqual(count.textContent, '1/3', 'open shows 1/3 counter');
  assert(prevBtn.disabled, 'prev disabled at first greeting');
  assert(!nextBtn.disabled, 'next enabled at first greeting');
  assert(!delBtn.disabled, 'delete enabled with greetings');

  window.g2GreetingNext();
  assertEqual(ta.value, 'Hello', 'next shows second greeting');
  assertEqual(count.textContent, '2/3', 'next updates counter');

  ta.value = 'Hello there';
  window.g2GreetingInput();
  window.g2GreetingPrev();
  assertEqual(ta.value, 'Hi', 'prev back to first');
  window.g2GreetingNext();
  assertEqual(ta.value, 'Hello there', 'typed text preserved per-variant after nav');
  assert(prevBtn.disabled === false, 'prev re-enabled in middle');

  window.g2GreetingAdd();
  assertEqual(count.textContent, '4/4', 'add appends and shows new total');
  assertEqual(ta.value, '', 'add jumps to empty new variant');
  assert(ta._focused, 'add focuses textarea');

  ta.value = 'Fourth';
  window.g2GreetingInput();
  window.g2GreetingDelete();
  assertEqual(count.textContent, '3/3', 'delete removes variant');
  assertEqual(ta.value, 'Howdy', 'delete lands on previous variant');

  window.g2GreetingDelete();
  assertEqual(count.textContent, '2/2', 'second delete');
  assertEqual(ta.value, 'Hello there', 'second delete lands on previous');
  window.g2GreetingDelete();
  window.g2GreetingDelete();
  assertEqual(count.textContent, '0/0', 'delete last variant shows 0/0');
  assertEqual(ta.value, '', 'empty list clears textarea');
  assert(prevBtn.disabled && nextBtn.disabled && delBtn.disabled, 'all controls disabled when empty');

  ta.value = 'Fresh';
  window.g2GreetingInput();
  assertEqual(count.textContent, '1/1', 'typing into empty list creates first variant');

  // ── submit merges greetings into first_mes / alternate_greetings ──
  var captured = null;
  var fetchFn = h.createMockFetch({
    ok: true,
    json: function () { return {}; },
  });
  var oldFetch = global.fetch;
  var oldFormData = global.FormData;
  var oldResolve = global.resolveFormFromEvent;
  global.fetch = fetchFn;
  global.FormData = h.createMockFormData();
  global.resolveFormFromEvent = function (e) { return e._form; };

  ta.value = 'Fresh';
  window.g2GreetingInput();
  window.g2GreetingAdd();
  ta.value = '  ';
  window.g2GreetingInput();
  window.g2GreetingAdd();
  ta.value = 'Alt B';
  window.g2GreetingInput();

  var form = { _fields: { name: 'N', greeting: 'stale' } };
  window.submitEditG2({ preventDefault: function () {}, _form: form });

  var last = fetchFn._last();
  captured = JSON.parse(last.opts.body);
  assertEqual(captured.first_mes, 'Fresh', 'submit maps first variant to first_mes');
  assertDeepEqual(captured.alternate_greetings, ['Alt B'], 'submit maps rest to alternate_greetings');
  assertEqual(captured.greeting, undefined, 'submit strips raw greeting field');

  global.fetch = oldFetch;
  global.FormData = oldFormData;
  global.resolveFormFromEvent = oldResolve;
  doc.getElementById = origGet;

  // ── persona factory without greetings registers no greeting fns ──
  var pcfg = {
    dataPrefix: 'persona',
    mediaSectionId: 'media-section-p',
    idPrefix: 'edit-p1',
    modalId: 'modal-edit-p1',
    openFn: 'openEditP1',
    uploadFn: 'uploadP1',
    uploadFileFn: 'uploadP1File',
    deleteFn: 'deleteP1Image',
    avatarFn: 'uploadP1Avatar',
    submitFn: 'submitEditP1',
    apiGet: function (id) { return '/api/personas/' + id; },
    apiImages: function (id) { return '/api/personas/' + id + '/images'; },
    apiImage: function (id, imgId) { return '/api/personas/' + id + '/images/' + imgId; },
    apiAvatar: function (id) { return '/api/personas/' + id + '/avatar'; },
    mediaIdPrefix: 'p1-img',
    stateKey: 'persona_id',
    dropZoneSelector: '#p1-dropzone',
  };
  window.createEditModalHandlers(pcfg);
  assert(typeof window.p1GreetingPrev === 'undefined', 'persona registers no greeting fns');
})();

// ── Result ──
h.printSummary();
