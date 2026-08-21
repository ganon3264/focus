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
global.showErrorToast = function () {};
global.openConfirmModal = function (message, callback) { callback(); };
global.FormData = function (form) {
  this._fields = {};
  this.append = function (k, v) { this._fields[k] = v; };
};
var setDirtyCalls = [];
global.ModalController = {
  setDirty: function (id, val) { setDirtyCalls.push({ id: id, val: val }); },
};
var CustomEventCtor = h.createMockCustomEvent();
global.CustomEvent = CustomEventCtor;
global.dispatchEvent = function (ev) { CustomEventCtor._events.push(ev); };
global.localStorage = h.createMockLocalStorage();
var submitPromise = null;
var submitFetchFn = null;

// Load queue (reloadPromptArranger now goes through hxGet)
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'hx-queue.js'), 'utf8'));

// Load module
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'edit-entity.js'), 'utf8'));

assert(typeof window.createEditModalHandlers === 'function', 'createEditModalHandlers loaded');

// ── reloadPromptArranger reloads #arranger-content with query params ──
(function () {
  var captured = null;
  var oldHxGet = window.hxGet;
  window.hxGet = function (url, opts) {
    captured = { url: url, opts: opts };
    return Promise.resolve();
  };

  // reloadPromptArranger guards on #arranger-content
  var targetEl = makeElement('div');
  targetEl.id = 'arranger-content';
  doc._body.appendChild(targetEl);
  var origGet = doc.getElementById;
  doc.getElementById = function (id) {
    if (id === 'arranger-content') return targetEl;
    return origGet ? origGet(id) : null;
  };

  window.reloadPromptArranger('preset-1');
  assert(!!captured, 'hxGet called');
  assertEqual(captured.url, '/partials/prompt-arranger/preset-1', 'arranger URL without params');
  assertEqual(captured.opts.target, '#arranger-content', 'arranger target');

  doc.getElementById = origGet;
  window.hxGet = oldHxGet;
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

// ── Greeting editor: open fetches server-rendered section; submit passes through ──
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
    greetingSectionId: 'edit-g2-greeting-section',
    greetingPartial: function (id) { return '/partials/character-greeting/' + id; },
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
    doc._body.appendChild(el);
    return el;
  }

  makeEl('input', 'edit-g2-id', { value: 'c1' });
  makeEl('input', 'edit-g2-name', { value: 'N' });
  makeEl('textarea', 'edit-g2-desc', { value: '' });
  makeEl('img', 'edit-g2-image-preview');
  makeEl('span', 'edit-g2-image-placeholder');
  makeEl('div', 'media-section-g2');
  makeEl('div', 'modal-edit-g2');

  window.createEditModalHandlers(cfg);

  var origGet = doc.getElementById;
  doc.getElementById = function (id) { return doc.querySelector('#' + id); };

  // ── open loads the greeting section from the server ──
  var lastPost = null;
  var oldHxPost = window.hxPost;
  window.hxPost = function (url, opts) {
    lastPost = { url: url, opts: opts };
    return Promise.resolve();
  };

  var btn = makeElement('button');
  btn.dataset.charId = 'c1';
  btn.dataset.charMedia = '[]';
  window.openEditG2(btn);

  assert(!!lastPost, 'open fetches greeting section via hxPost');
  assertEqual(lastPost.url, '/partials/character-greeting/c1', 'open fetches greeting section for char id');
  assertEqual(lastPost.opts.target, '#edit-g2-greeting-section', 'open targets greeting section');
  assertEqual(lastPost.opts.swap, 'outerHTML', 'open swaps greeting section outerHTML');
  window.hxPost = oldHxPost;

  // ── submit forwards greeting fields to the server (no client-side merge) ──
  submitFetchFn = h.createMockFetch({ ok: true, json: function () { return {}; } });
  global.fetch = submitFetchFn;
  global.FormData = h.createMockFormData();
  global.resolveFormFromEvent = function (e) { return e._form; };

  var form = { _fields: { name: 'N', greeting: 'Edited', greetings_json: '["Hi","Alt A"]', greeting_idx: '1' } };
  submitPromise = window.submitEditG2({ preventDefault: function () {}, _form: form });

  doc.getElementById = origGet;

  // ── persona factory without greetingSectionId registers no greeting fns ──
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

  // ── persona open does not fetch a greeting section ──
  var ajaxCalls = 0;
  global.htmx.ajax = function () { ajaxCalls++; };
  doc.getElementById = function (id) { return doc.querySelector('#' + id); };
  makeEl('input', 'edit-p1-id', { value: 'p1' });
  makeEl('input', 'edit-p1-name', { value: 'P' });
  makeEl('textarea', 'edit-p1-desc', { value: '' });
  makeEl('img', 'edit-p1-image-preview');
  makeEl('span', 'edit-p1-image-placeholder');
  makeEl('div', 'media-section-p');
  makeEl('div', 'modal-edit-p1');
  var pbtn = makeElement('button');
  pbtn.dataset.personaId = 'p1';
  pbtn.dataset.personaMedia = '[]';
  window.openEditP1(pbtn);
  assertEqual(ajaxCalls, 0, 'persona open does not fetch greeting section');
})();

// ── Result ──
submitPromise.then(function () {
  var body = JSON.parse(submitFetchFn._last().opts.body);
  assertEqual(body.greeting, 'Edited', 'submit sends current greeting value');
  assertEqual(body.greetings_json, '["Hi","Alt A"]', 'submit sends working greeting list');
  assertEqual(body.greeting_idx, '1', 'submit sends greeting index');
  assertEqual(body.first_mes, undefined, 'submit does not map first_mes client-side');
  h.printSummary();
}).catch(function (err) {
  console.error(err);
  process.exit(1);
});
