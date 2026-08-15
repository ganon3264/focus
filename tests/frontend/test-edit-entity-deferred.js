// Unit tests for edit-entity.js — deferred attachments/avatar + greeting dirty
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

var doc = h.createMockDocument();
doc.body = doc._body;
doc.body.addEventListener = function () {};
doc._handlers = {};
doc.addEventListener = function (type, fn) {
  (doc._handlers[type] = doc._handlers[type] || []).push(fn);
};
doc.createElement = function (tag) {
  var el = h.makeElement(tag);
  el.style = {};
  el.appendChild = function (c) {
    var idx = this.children.indexOf(c); if (idx >= 0) this.children.splice(idx, 1);
    this.children.push(c); c.parent = this; return c;
  };
  return el;
};

var setDirtyCalls = [];
var greetingDirtyCalls = [];
var openCalls = [];
var fetchCalls = [];
var thumbCount = 0;

global.window = global;
global.document = doc;
global.fetch = function (url, opts) {
  fetchCalls.push({ url: url, opts: opts });
  return Promise.resolve({ ok: true, json: function () { return Promise.resolve({ id: 'img-new' }); } });
};
global.alert = function () {};
global.htmx = { ajax: function () { return Promise.resolve(); } };
global.StateManager = { get: function () { return null; } };
global.openCropModal = function (file, cb) { cb({ blob: true }); };
global.setupDropZone = function () {};
global.buildMediaThumbnail = function (img, onDelete, idPrefix) {
  thumbCount++;
  var el = doc.createElement('div');
  el.dataset.imageId = img.id;
  return el;
};
global.openModal = function () { openCalls.push(true); };
global.closeModal = function () {};
global.showSuccessToast = function () {};
global.showInfoToast = function () {};
global.showErrorToast = function () {};
global.openConfirmModal = function (message, callback) { callback(); };
global.FormData = h.createMockFormData();
global.resolveFormFromEvent = function (e) { return e._form; };
global.ModalController = {
  setDirty: function (id, val) { setDirtyCalls.push({ id: id, val: val }); },
  setGreetingDirty: function (id, val) { greetingDirtyCalls.push({ id: id, val: val }); },
};
var CustomEventCtor = h.createMockCustomEvent();
global.CustomEvent = CustomEventCtor;
global.dispatchEvent = function (ev) { CustomEventCtor._events.push(ev); };
global.localStorage = h.createMockLocalStorage();

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'edit-entity.js'), 'utf8'));

function makeEl(tag, id, opts) {
  opts = opts || {};
  var el = makeElement(tag);
  el.id = id;
  el.style = {};
  if (opts.value !== undefined) el.value = opts.value;
  if (opts.cls) el.className = opts.cls;
  doc._body.appendChild(el);
  return el;
}

var ccfg = {
  dataPrefix: 'char',
  mediaSectionId: 'edit-char-media-section',
  idPrefix: 'edit-char',
  modalId: 'modal-edit-character',
  openFn: 'openEditChar',
  uploadFn: 'uploadCharModalMedia',
  uploadFileFn: 'uploadCharModalMediaFile',
  deleteFn: 'deleteCharModalMedia',
  avatarFn: 'uploadCharacterAvatar',
  submitFn: 'submitEditCharacter',
  greetingSectionId: 'edit-char-greeting-section',
  greetingPartial: function (id) { return '/partials/character-greeting/' + id; },
  apiGet: function (id) { return '/api/characters/' + id; },
  apiImages: function (id) { return '/api/characters/' + id + '/images'; },
  apiImage: function (id, imgId) { return '/api/characters/' + id + '/images/' + imgId; },
  apiAvatar: function (id) { return '/api/characters/' + id + '/avatar'; },
  mediaIdPrefix: 'char-modal-media',
  stateKey: 'character_id',
  dropZoneSelector: '#edit-char-media-section',
};

function flush() {
  return new Promise(function (r) { setTimeout(r, 0); });
}

(async function main() {
  // Build a minimal char edit modal DOM.
  makeEl('input', 'edit-char-id', { value: 'c1' });
  makeEl('input', 'edit-char-name', { value: 'N' });
  makeEl('textarea', 'edit-char-desc', { value: '' });
  makeEl('img', 'edit-char-image-preview');
  makeEl('span', 'edit-char-image-placeholder');

  var media = makeEl('div', 'edit-char-media-section');
  var addBtn = makeEl('label', '', { cls: 'block-media-btn' });
  media.appendChild(addBtn);
  var ph = makeEl('span', '', { cls: 'block-media-placeholder' });
  media.appendChild(ph);

  var gsec = makeEl('div', 'edit-char-greeting-section');
  var gta = makeEl('textarea', 'edit-char-greeting', { value: 'Hello' });
  gta.setAttribute('name', 'greeting');
  gsec.appendChild(gta);
  var gj = makeEl('input', '', { value: '["Hello","Alt A"]' });
  gj.setAttribute('name', 'greetings_json');
  gsec.appendChild(gj);
  var gidx = makeEl('input', '', { value: '0' });
  gidx.setAttribute('name', 'greeting_idx');
  gsec.appendChild(gidx);

  window.createEditModalHandlers(ccfg);
  assert(typeof window.actionGreetingInput === 'function', 'greeting input handler registered');

  // ── open stages existing media, does not fetch anything yet ──
  var btn = makeElement('button');
  btn.dataset.charId = 'c1';
  btn.dataset.charMedia = '[{"id":"img1","image_path":"a.png","mime_type":"image/png"}]';
  window.openEditChar(btn);

  // Simulate the greeting section landing. htmx fires htmx:afterSwap
  // synchronously inside the XHR onload, before the ajax() promise resolves.
  (doc._handlers['htmx:afterSwap'] || []).forEach(function (fn) {
    fn({ detail: { target: gsec } });
  });

  await flush();

  assertEqual(fetchCalls.length, 0, 'open issues no attachment fetch');
  assertEqual(thumbCount, 1, 'open renders existing media thumbnail');
  assertEqual(setDirtyCalls.length, 0, 'open leaves modal clean');
  assertEqual(greetingDirtyCalls.length, 0, 'open-load swap baselines greeting without marking dirty');
  assertEqual(openCalls.length, 1, 'open opens the modal');

  // ── greeting input marks dirty; revert clears ──
  greetingDirtyCalls.length = 0;
  gta.value = 'Hello world';
  window.actionGreetingInput(gta);
  assertEqual(greetingDirtyCalls.length, 1, 'greeting edit marks dirty');
  assertEqual(greetingDirtyCalls[0].val, true, 'greeting edit dirty=true');

  greetingDirtyCalls.length = 0;
  gta.value = 'Hello';
  window.actionGreetingInput(gta);
  assertEqual(greetingDirtyCalls[0].val, false, 'greeting revert clears dirty');

  // ── CRLF in stored greetings normalizes before comparison ──
  greetingDirtyCalls.length = 0;
  gj.value = '["Hello","Alt\\r\\nA"]';
  gidx.value = '0';
  gta.value = 'Hello';
  window.openEditChar(btn);
  (doc._handlers['htmx:afterSwap'] || []).forEach(function (fn) {
    fn({ detail: { target: gsec } });
  });
  await flush();
  greetingDirtyCalls.length = 0;

  // swipe to greeting 2: server echoes CRLF in JSON, textarea value is LF
  gidx.value = '1';
  gta.value = 'Alt\nA';
  (doc._handlers['htmx:afterSwap'] || []).forEach(function (fn) {
    fn({ detail: { target: gsec } });
  });
  assertEqual(greetingDirtyCalls.length, 1, 'CRLF nav recomputes dirty');
  assertEqual(greetingDirtyCalls[0].val, false, 'CRLF greeting nav does not mark dirty');

  // ── upload stages locally (no fetch), marks dirty ──
  setDirtyCalls.length = 0;
  window.uploadCharModalMediaFile({ type: 'image/png' });
  assertEqual(fetchCalls.length, 0, 'upload does not hit server immediately');
  assertEqual(setDirtyCalls.length, 1, 'upload marks dirty');
  assertEqual(setDirtyCalls[0].val, true, 'upload dirty=true');

  // ── delete stages locally (no fetch), marks dirty ──
  setDirtyCalls.length = 0;
  window.deleteCharModalMedia('img1');
  assertEqual(fetchCalls.length, 0, 'delete does not hit server immediately');
  assertEqual(setDirtyCalls.length, 1, 'delete marks dirty');
  assertEqual(setDirtyCalls[0].val, true, 'delete dirty=true');

  // ── avatar stages locally (no fetch), marks dirty ──
  setDirtyCalls.length = 0;
  window.uploadCharacterAvatar({ files: [{ type: 'image/png' }], value: '' });
  assertEqual(fetchCalls.length, 0, 'avatar does not hit server immediately');
  assertEqual(setDirtyCalls.length, 1, 'avatar marks dirty');

  // ── save commits in order: upload → delete → PATCH (fresh open clears avatar) ──
  window.openEditChar(btn);
  await flush();
  setDirtyCalls.length = 0;
  fetchCalls.length = 0;

  window.uploadCharModalMediaFile({ type: 'image/png' });
  window.deleteCharModalMedia('img1');

  var form = { _fields: { name: 'N', description: '', greeting: 'Hello', greetings_json: '["Hello","Alt A"]', greeting_idx: '0' } };
  var p = window.submitEditCharacter({ preventDefault: function () {}, _form: form });
  assert(p && typeof p.then === 'function', 'submit returns a promise');
  await flush();

  assertEqual(fetchCalls.length, 3, 'save issues upload + delete + PATCH');
  assertEqual(fetchCalls[0].url, '/api/characters/c1/images', 'save uploads staged file first');
  assertEqual(fetchCalls[0].opts.method, 'POST', 'upload uses POST');
  assertEqual(fetchCalls[1].url, '/api/characters/c1/images/img1', 'save deletes removed image');
  assertEqual(fetchCalls[1].opts.method, 'DELETE', 'delete uses DELETE');
  assertEqual(fetchCalls[2].url, '/api/characters/c1', 'save patches form last');
  assertEqual(fetchCalls[2].opts.method, 'PATCH', 'patch uses PATCH');

  // ── greeting partial failure still opens the modal ──
  var oldAjax = global.htmx.ajax;
  global.htmx.ajax = function () { return Promise.reject(new Error('boom')); };
  openCalls.length = 0;
  greetingDirtyCalls.length = 0;
  window.openEditChar(btn);
  await flush();
  assertEqual(openCalls.length, 1, 'greeting fetch failure still opens modal');

  // baseline never captured → greeting input is a no-op (no crash, no dirty)
  gta.value = 'whatever';
  window.actionGreetingInput(gta);
  assertEqual(greetingDirtyCalls.length, 0, 'failed load: greeting input ignored (no baseline)');
  global.htmx.ajax = oldAjax;

  h.printSummary();
})().catch(function (err) {
  console.error(err);
  process.exit(1);
});
