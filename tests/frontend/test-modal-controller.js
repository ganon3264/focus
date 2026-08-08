// Unit tests for ui/modal.js — ModalController lifecycle (open/close/stack/ESC/dirty)
var h = require('./helpers.js');
var assert = h.assert;
var assertEqual = h.assertEqual;
var assertIncludes = h.assertIncludes;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

var doc = h.createMockDocument();
doc.addEventListener = function (type, fn) {
  this._handlers = this._handlers || {};
  (this._handlers[type] = this._handlers[type] || []).push(fn);
};

var CustomEventCtor = h.createMockCustomEvent();
var dispatched = CustomEventCtor._events;
var confirmCalls = [];

global.window = global;
global.document = doc;
global.CustomEvent = CustomEventCtor;
global.dispatchEvent = function (ev) { dispatched.push(ev); };
global.openConfirmModal = function (msg, cb) { confirmCalls.push({ msg: msg, cb: cb }); };
global.closeConfirmModal = function () {};
global.htmx = { ajax: function () {} };
global.StateManager = { get: function () { return null; } };
global.api = { partials: { charactersModal: '', personasModal: '', providersModal: '' } };
global.BackupManager = null;

function enableEvents(el) {
  el.addEventListener = function (t, fn) {
    this._handlers = this._handlers || {};
    (this._handlers[t] = this._handlers[t] || []).push(fn);
  };
  el.dispatchEvent = function (ev) {
    var hs = this._handlers && this._handlers[ev.type];
    if (hs) hs.forEach(function (fn) { fn(ev); });
    return true;
  };
  return el;
}

function dispatchKey(key) {
  var hs = doc._handlers && doc._handlers.keydown || [];
  hs.forEach(function (fn) { fn({ key: key, keyCode: key === 'Escape' ? 27 : 0 }); });
}

function makeModal(id, fieldsAttr, label) {
  var ov = enableEvents(makeElement('div'));
  ov.id = id;
  ov.classList.add('modal-overlay');
  ov.classList.add('hidden');
  if (fieldsAttr) ov.setAttribute('data-dirty-fields', fieldsAttr);
  if (label) ov.setAttribute('data-dirty-label', label);
  var hint = makeElement('span');
  hint.setAttribute('data-dirty-hint', '');
  var save = makeElement('button');
  save.setAttribute('data-dirty-save', '');
  ov.appendChild(hint);
  ov.appendChild(save);
  doc._body.appendChild(ov);
  return ov;
}

function addField(ov, id, value, cls) {
  var f = makeElement('input');
  f.id = id;
  f.className = cls || 'edit-field';
  f.value = value || '';
  ov.appendChild(f);
  return f;
}

function type(ov, field, value) {
  field.value = value;
  ov.dispatchEvent({ type: 'input' });
}

function hintOf(ov) { return ov.querySelector('[data-dirty-hint]'); }
function saveOf(ov) { return ov.querySelector('[data-dirty-save]'); }

var MODAL_JS = path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'modal.js');
eval(fs.readFileSync(MODAL_JS, 'utf8'));

assert(typeof window.ModalController === 'object', 'ModalController loaded');
assert(typeof window.openModal === 'function', 'openModal wrapper loaded');
assert(typeof window.closeModal === 'function', 'closeModal wrapper loaded');

// ── open captures a clean snapshot (no spurious dirty) ──
(function () {
  var ov = makeModal('modal-clean', '.edit-field', 'this message');
  var f = addField(ov, 'edit-field-a', 'Hello');
  addField(ov, 'edit-field-b', 'World');

  window.openModal('modal-clean');

  assert(!ov.classList.contains('hidden'), 'open: overlay visible');
  assertEqual(window.ModalController.isOpen('modal-clean'), true, 'open: tracked in stack');
  assertEqual(window.ModalController.isDirty('modal-clean'), false, 'open: clean snapshot');
  assert(hintOf(ov).classList.contains('hidden'), 'open: hint hidden');
  assertEqual(saveOf(ov).disabled, true, 'open: save disabled');
  assertEqual(f.value, 'Hello', 'open: field intact');
  window.closeModal('modal-clean', { discard: true });
})();

// ── typing marks dirty; reverting clears ──
(function () {
  var ov = makeModal('modal-typing', '.edit-field');
  var f = addField(ov, 'edit-field-a', 'Hello');
  window.openModal('modal-typing');
  dispatched.length = 0;

  type(ov, f, 'Hello world');
  assertEqual(window.ModalController.isDirty('modal-typing'), true, 'typing: dirty');
  assert(!hintOf(ov).classList.contains('hidden'), 'typing: hint shown');
  assertEqual(saveOf(ov).disabled, false, 'typing: save enabled');
  assertEqual(dispatched.length, 1, 'typing: dirty-changed emitted');
  assertEqual(dispatched[0].detail.id, 'modal-typing', 'typing: event id');
  assertEqual(dispatched[0].detail.dirty, true, 'typing: event dirty=true');

  type(ov, f, 'Hello');
  assertEqual(window.ModalController.isDirty('modal-typing'), false, 'revert: clean');
  assert(hintOf(ov).classList.contains('hidden'), 'revert: hint hidden');
  assertEqual(saveOf(ov).disabled, true, 'revert: save disabled');
  window.closeModal('modal-typing', { discard: true });
})();

// ── close clean: no confirm, closes directly ──
(function () {
  var ov = makeModal('modal-close-clean', '.edit-field');
  addField(ov, 'edit-field-a', 'x');
  window.openModal('modal-close-clean');
  confirmCalls.length = 0;

  window.closeModal('modal-close-clean');
  assertEqual(confirmCalls.length, 0, 'close clean: no confirm');
  assert(ov.classList.contains('hidden'), 'close clean: hidden');
  assertEqual(window.ModalController.isOpen('modal-close-clean'), false, 'close clean: popped');
})();

// ── close dirty: confirm dialog; callback closes; cancel keeps open ──
(function () {
  var ov = makeModal('modal-confirm', '.edit-field', '#edit-label');
  addField(ov, 'edit-label', 'My Name');
  addField(ov, 'edit-field-a', 'x');
  window.openModal('modal-confirm');
  confirmCalls.length = 0;

  var f = ov.querySelector('#edit-label');
  type(ov, f, 'Edited Name');
  window.closeModal('modal-confirm');
  assertEqual(confirmCalls.length, 1, 'close dirty: confirm asked');
  assertIncludes(confirmCalls[0].msg, 'Edited Name', 'close dirty: label resolved from selector');
  assert(!ov.classList.contains('hidden'), 'close dirty: still open before confirm');

  confirmCalls[0].cb();
  assert(ov.classList.contains('hidden'), 'close dirty: closed after confirm');
  assertEqual(window.ModalController.isDirty('modal-confirm'), false, 'close dirty: state cleared');
})();

// ── close dirty with discard: no confirm ──
(function () {
  var ov = makeModal('modal-discard', '.edit-field');
  var f = addField(ov, 'edit-field-a', 'x');
  window.openModal('modal-discard');
  type(ov, f, 'y');
  confirmCalls.length = 0;

  window.closeModal('modal-discard', { discard: true });
  assertEqual(confirmCalls.length, 0, 'discard close: no confirm');
  assert(ov.classList.contains('hidden'), 'discard close: hidden');
})();

// ── setDirty (attachments) ──
(function () {
  var ov = makeModal('modal-forced', '.edit-field');
  addField(ov, 'edit-field-a', 'x');
  window.openModal('modal-forced');

  window.ModalController.setDirty('modal-forced', true);
  assertEqual(window.ModalController.isDirty('modal-forced'), true, 'setDirty true');
  assert(!hintOf(ov).classList.contains('hidden'), 'setDirty true: hint shown');

  window.ModalController.setDirty('modal-forced', false);
  assertEqual(window.ModalController.isDirty('modal-forced'), false, 'setDirty false');
  window.closeModal('modal-forced', { discard: true });
})();

// ── lazy baseline: fields added after open are clean until changed ──
(function () {
  var ov = makeModal('modal-late', '.late-field');
  window.openModal('modal-late');
  var late = makeElement('textarea');
  late.className = 'late-field';
  late.id = 'late-1';
  late.value = 'seed';
  ov.appendChild(late);

  window.ModalController.refresh('modal-late');
  assertEqual(window.ModalController.isDirty('modal-late'), false, 'late field: baselined clean');

  late.value = 'changed';
  window.ModalController.refresh('modal-late');
  assertEqual(window.ModalController.isDirty('modal-late'), true, 'late field: change detected');
  window.closeModal('modal-late', { discard: true });
})();

// ── reopen re-captures: stale dirty does not survive close ──
(function () {
  var ov = makeModal('modal-reopen', '.edit-field');
  var f = addField(ov, 'edit-field-a', 'base');
  window.openModal('modal-reopen');
  type(ov, f, 'edited');
  assertEqual(window.ModalController.isDirty('modal-reopen'), true, 'reopen: dirty before close');

  window.closeModal('modal-reopen', { discard: true });
  window.openModal('modal-reopen');
  assertEqual(window.ModalController.isDirty('modal-reopen'), false, 'reopen: clean after reopen');
  assertEqual(saveOf(ov).disabled, true, 'reopen: save disabled again');
  window.closeModal('modal-reopen', { discard: true });
})();

// ── open twice: single stack entry; ESC closes it ──
(function () {
  var ov = makeModal('modal-twice', '.edit-field');
  addField(ov, 'edit-field-a', 'x');
  window.openModal('modal-twice');
  window.openModal('modal-twice');

  dispatchKey('Escape');
  assert(ov.classList.contains('hidden'), 'open twice + ESC: closed exactly once');
})();

// ── open while already visible does not re-baseline in-progress edits ──
(function () {
  var ov = makeModal('modal-visible', '.edit-field');
  var f = addField(ov, 'edit-field-a', 'x');
  window.openModal('modal-visible');
  type(ov, f, 'edited');

  window.openModal('modal-visible');
  assertEqual(window.ModalController.isDirty('modal-visible'), true, 'open while visible: dirty preserved');
  window.closeModal('modal-visible', { discard: true });
})();

// ── ESC closes topmost of stacked modals ──
(function () {
  var a = makeModal('modal-esc-a', '.edit-field');
  var b = makeModal('modal-esc-b', '.edit-field');
  addField(a, 'edit-field-a', 'x');
  addField(b, 'edit-field-b', 'y');
  window.openModal('modal-esc-a');
  window.openModal('modal-esc-b');

  dispatchKey('Escape');
  assert(b.classList.contains('hidden'), 'ESC: topmost closed');
  assert(!a.classList.contains('hidden'), 'ESC: underlying still open');

  dispatchKey('Escape');
  assert(a.classList.contains('hidden'), 'ESC: next closed');
})();

// ── ESC closes confirm modal first, leaving the modal open ──
(function () {
  var confirmEl = enableEvents(makeElement('div'));
  confirmEl.id = 'global-confirm-modal';
  confirmEl.classList.add('modal-overlay');
  confirmEl.classList.add('hidden');
  doc._body.appendChild(confirmEl);
  var confirmClosed = 0;
  global.closeConfirmModal = function () {
    confirmEl.classList.add('hidden');
    confirmClosed++;
  };

  var ov = makeModal('modal-esc-confirm', '.edit-field');
  var f = addField(ov, 'edit-field-a', 'x');
  window.openModal('modal-esc-confirm');
  type(ov, f, 'edited');
  confirmEl.classList.remove('hidden');

  dispatchKey('Escape');
  assertEqual(confirmClosed, 1, 'ESC: confirm modal closed first');
  assert(!ov.classList.contains('hidden'), 'ESC: underlying modal stays open');
  assertEqual(window.ModalController.isDirty('modal-esc-confirm'), true, 'ESC: dirty state intact');

  confirmEl.classList.add('hidden');
  window.closeModal('modal-esc-confirm', { discard: true });
})();

// ── ESC with nothing open closes lightbox ──
(function () {
  var lb = makeElement('div');
  lb.id = 'lightbox';
  lb.classList.add('hidden');
  doc._body.appendChild(lb);
  var lbClosed = 0;
  global.closeLightbox = function () { lbClosed++; };

  lb.classList.remove('hidden');
  dispatchKey('Escape');
  assertEqual(lbClosed, 1, 'ESC: lightbox closed when no modals open');

  lb.classList.add('hidden');
})();

// ── onOpen hooks fire only on hidden→visible transition ──
(function () {
  var fired = 0;
  window.ModalController.onOpen('modal-hooked', function () { fired++; });
  var ov = makeModal('modal-hooked');
  window.openModal('modal-hooked');
  window.openModal('modal-hooked');
  assertEqual(fired, 1, 'onOpen: fired once despite double open');
  window.closeModal('modal-hooked', { discard: true });
})();

// ── refresh recomputes from DOM without input events (custom selects) ──
(function () {
  var ov = makeModal('modal-refresh', '.edit-field');
  var f = addField(ov, 'edit-field-a', 'x');
  window.openModal('modal-refresh');

  f.value = 'changed programmatically';
  window.ModalController.refresh('modal-refresh');
  assertEqual(window.ModalController.isDirty('modal-refresh'), true, 'refresh: detects programmatic change');

  f.value = 'x';
  window.ModalController.refresh('modal-refresh');
  assertEqual(window.ModalController.isDirty('modal-refresh'), false, 'refresh: reverting clean');
  window.closeModal('modal-refresh', { discard: true });
})();

// ── unknown ids and non-dirty modals are no-ops ──
(function () {
  window.openModal('modal-does-not-exist');
  window.closeModal('modal-does-not-exist');

  var ov = makeModal('modal-no-dirty');
  window.openModal('modal-no-dirty');
  assertEqual(window.ModalController.isDirty('modal-no-dirty'), false, 'no dirty fields: never dirty');
  assert(!ov.classList.contains('hidden'), 'no dirty fields: still opens');
  assertEqual(saveOf(ov).disabled, true, 'no dirty fields: save untouched');

  window.closeModal('modal-no-dirty');
  assert(ov.classList.contains('hidden'), 'no dirty fields: closes');
})();

// ── overlay replaced by htmx swap re-registers (providers modal body) ──
(function () {
  var ov = makeModal('modal-swapped', '.edit-field');
  window.openModal('modal-swapped');
  window.closeModal('modal-swapped', { discard: true });
  ov.remove();

  var fresh = makeModal('modal-swapped', '.edit-field');
  var f = addField(fresh, 'edit-field-a', 'seed');
  window.openModal('modal-swapped');
  type(fresh, f, 'edited');
  assertEqual(window.ModalController.isDirty('modal-swapped'), true, 'swapped overlay: dirty tracking works');
  window.closeModal('modal-swapped', { discard: true });
})();

h.printSummary();
