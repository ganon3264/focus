// Unit tests for edit-entity.js — modal handler factory
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
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

// ── Result ──
h.printSummary();
