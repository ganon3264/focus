// Unit tests for ui/confirm.js — confirm dialog driven through ModalController
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

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

var doc = h.createMockDocument();
var CustomEventCtor = h.createMockCustomEvent();
doc._handlers = {};
doc.addEventListener = function (type, fn) {
  (this._handlers[type] = this._handlers[type] || []).push(fn);
};

global.window = global;
global.document = doc;
global.CustomEvent = CustomEventCtor;
global.dispatchEvent = function () {};
global.htmx = { ajax: function () {} };
global.StateManager = { get: function () { return null; } };
global.api = { partials: { charactersModal: '', personasModal: '', providersModal: '' } };
global.BackupManager = null;

var confirmOverlay = enableEvents(makeElement('div'));
confirmOverlay.id = 'global-confirm-modal';
confirmOverlay.classList.add('modal-overlay');
confirmOverlay.classList.add('hidden');
confirmOverlay.dataset.ui = 'modal-overlay';
var confirmMessage = makeElement('div');
confirmMessage.id = 'global-confirm-message';
var confirmBtn = enableEvents(makeElement('button'));
confirmBtn.id = 'global-confirm-btn';
confirmOverlay.appendChild(confirmMessage);
confirmOverlay.appendChild(confirmBtn);
doc._body.appendChild(confirmOverlay);
doc.getElementById = function (id) {
  if (id === 'global-confirm-modal') return confirmOverlay;
  if (id === 'global-confirm-message') return confirmMessage;
  if (id === 'global-confirm-btn') return confirmBtn;
  return doc.querySelector('#' + id);
};

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'modal.js'), 'utf8'));
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'confirm.js'), 'utf8'));

function dispatchKey(key) {
  var hs = doc._handlers.keydown || [];
  hs.forEach(function (fn) { fn({ key: key, keyCode: key === 'Escape' ? 27 : 0 }); });
}

// ── open opens through the controller and renders the message ──
(function () {
  window.openConfirmModal('Delete this?', null);
  assert(!confirmOverlay.classList.contains('hidden'), 'open: overlay visible');
  assertEqual(window.ModalController.isOpen('global-confirm-modal'), true, 'open: pushed on the stack');
  assertEqual(confirmMessage.textContent, 'Delete this?', 'open: message text set');
})();

// ── confirm button fires the callback and closes ──
(function () {
  var called = 0;
  window.openConfirmModal('Proceed?', function () { called++; });
  confirmBtn.dispatchEvent({ type: 'click' });
  assertEqual(called, 1, 'confirm: callback invoked');
  assertEqual(window.ModalController.isOpen('global-confirm-modal'), false, 'confirm: closed after accept');
  assert(confirmOverlay.classList.contains('hidden'), 'confirm: overlay hidden after accept');
})();

// ── closeConfirmModal drops the pending callback ──
(function () {
  var called = 0;
  window.openConfirmModal('Cancel me', function () { called++; });
  window.closeConfirmModal();
  assertEqual(window.ModalController.isOpen('global-confirm-modal'), false, 'cancel: popped off the stack');
  assert(confirmOverlay.classList.contains('hidden'), 'cancel: overlay hidden');

  confirmBtn.dispatchEvent({ type: 'click' });
  assertEqual(called, 0, 'cancel: stale callback never runs');
})();

// ── close on a closed dialog is a no-op ──
(function () {
  window.closeConfirmModal();
  assertEqual(window.ModalController.isOpen('global-confirm-modal'), false, 'close when closed: still closed');
  assert(confirmOverlay.classList.contains('hidden'), 'close when closed: overlay stays hidden');
})();

// ── HTML messages keep the innerHTML path ──
(function () {
  window.openConfirmModal('Discard <b>now</b>?', null);
  assert(confirmMessage.innerHTML.indexOf('<b>now</b>') !== -1, 'open: HTML message rendered as markup');
  window.closeConfirmModal();
})();

// ── empty message falls back to the default text ──
(function () {
  window.openConfirmModal('', null);
  assertEqual(confirmMessage.textContent, 'Are you sure?', 'open: default message');
  window.closeConfirmModal();
})();

// ── confirm sits on top of a dirty modal: ESC dismisses it and keeps the rest ──
(function () {
  var ov = makeElement('div');
  ov.id = 'modal-dirty';
  ov.classList.add('modal-overlay');
  ov.classList.add('hidden');
  ov.dataset.ui = 'modal-overlay';
  ov.setAttribute('data-dirty-fields', '.edit-field');
  enableEvents(ov);
  var field = makeElement('input');
  field.className = 'edit-field';
  field.value = 'base';
  ov.appendChild(field);
  doc._body.appendChild(ov);

  window.openModal('modal-dirty');
  field.value = 'edited';
  ov.dispatchEvent({ type: 'input' });
  assertEqual(window.ModalController.isDirty('modal-dirty'), true, 'dirty modal: dirty after edit');

  window.closeModal('modal-dirty');
  assertEqual(window.ModalController.isOpen('global-confirm-modal'), true, 'dirty close: confirm opened');
  assert(!ov.classList.contains('hidden'), 'dirty close: modal still open behind confirm');

  dispatchKey('Escape');
  assertEqual(window.ModalController.isOpen('global-confirm-modal'), false, 'ESC: confirm dismissed first');
  assert(!ov.classList.contains('hidden'), 'ESC: dirty modal survives the dismissal');
  assertEqual(window.ModalController.isDirty('modal-dirty'), true, 'ESC: dirty state intact');

  window.closeModal('modal-dirty', { discard: true });
  assert(ov.classList.contains('hidden'), 'discard close: modal hidden');
})();

// ── ESC with no confirm open closes the topmost modal instead ──
(function () {
  window.openConfirmModal('still here', null);
  window.closeConfirmModal();

  var ov = makeElement('div');
  ov.id = 'modal-plain';
  ov.classList.add('modal-overlay');
  ov.classList.add('hidden');
  ov.dataset.ui = 'modal-overlay';
  doc._body.appendChild(ov);
  window.openModal('modal-plain');

  dispatchKey('Escape');
  assert(ov.classList.contains('hidden'), 'ESC: topmost modal closed');
  assertEqual(window.ModalController.isOpen('global-confirm-modal'), false, 'ESC: confirm not re-opened');
})();

// ── htmx:confirm without a question leaves the request alone ──
(function () {
  var prevented = 0;
  var issued = [];
  var ev = {
    type: 'htmx:confirm',
    detail: { question: null, issueRequest: function (v) { issued.push(v); } },
    preventDefault: function () { prevented++; },
  };
  (doc._handlers['htmx:confirm'] || []).forEach(function (fn) { fn(ev); });
  assertEqual(prevented, 0, 'htmx:confirm: no question means no preventDefault');
  assertEqual(issued.length, 0, 'htmx:confirm: no question means no re-issue');
  assertEqual(window.ModalController.isOpen('global-confirm-modal'), false, 'htmx:confirm: no dialog for a plain request');
})();

// ── htmx:confirm with a question prompts, then issues on accept ──
(function () {
  var prevented = 0;
  var issued = [];
  var ev = {
    type: 'htmx:confirm',
    detail: { question: 'Delete it?', issueRequest: function (v) { issued.push(v); } },
    preventDefault: function () { prevented++; },
  };
  (doc._handlers['htmx:confirm'] || []).forEach(function (fn) { fn(ev); });
  assertEqual(prevented, 1, 'htmx:confirm: question holds the request');
  assertEqual(issued.length, 0, 'htmx:confirm: nothing issued before the answer');
  assertEqual(confirmMessage.textContent, 'Delete it?', 'htmx:confirm: question rendered');

  confirmBtn.dispatchEvent({ type: 'click' });
  assertEqual(issued.length, 1, 'htmx:confirm: accepted request re-issued');
  assertEqual(issued[0], true, 'htmx:confirm: re-issued past the confirm hook');
})();

h.printSummary();
