// Unit tests for dirty-state.js — modal dirty tracking (field comparison)
var h = require('./helpers.js');
var assert = h.assert;
var assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var doc = h.createMockDocument();
global.window = global;
global.document = doc;

var fs = require('fs');
var path = require('path');
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'dirty-state.js'), 'utf8'));

assert(typeof window.dirtyModalState === 'function', 'dirtyModalState loaded');

function makeEl(tag) {
  var el = makeElement(tag);
  el.nodeType = 1;
  return el;
}

function setup(fields, label) {
  var overlay = makeEl('div');
  overlay.id = 'modal-edit';
  overlay.classList.add('modal-overlay');
  var form = makeEl('form');
  form.id = 'edit-form';
  var nameInput = makeEl('input');
  nameInput.id = 'edit-name';
  nameInput.value = '';
  var desc = makeEl('textarea');
  desc.id = 'edit-desc';
  desc.value = '';
  form.appendChild(nameInput);
  form.appendChild(desc);
  overlay.appendChild(form);
  doc._body.appendChild(overlay);

  var state = window.dirtyModalState({
    fields: fields || ['#edit-name', '#edit-desc'],
    label: label === undefined ? '#edit-name' : label,
  });
  state.$el = form;
  state.init();

  return { state: state, form: form, nameInput: nameInput, desc: desc };
}

// ── init / typing / revert / capture ──
(function () {
  var s = setup();
  assertEqual(s.state.dirty, false, 'init: clean');
  assertEqual(window._dirtyChecks['modal-edit'].isDirty(), false, 'init: registered check is clean');

  s.nameInput.value = 'New';
  s.state.markDirty();
  assertEqual(s.state.dirty, true, 'typing name: dirty');
  s.nameInput.value = '';
  s.state.markDirty();
  assertEqual(s.state.dirty, false, 'reverting name: clean');

  s.desc.value = 'desc';
  s.state.markDirty();
  assertEqual(s.state.dirty, true, 'typing desc: dirty');

  window.captureDirty('modal-edit');
  assertEqual(s.state.dirty, false, 'capture: clean');
  assertEqual(window.captureDirty('nonexistent'), undefined, 'capture: unknown id no-op');
})();

// ── refreshDirty: recompute from DOM without input events ──
(function () {
  var s = setup();
  s.nameInput.value = 'Changed';
  window.refreshDirty('modal-edit');
  assertEqual(s.state.dirty, true, 'refreshDirty: detects programmatic change');
  s.nameInput.value = '';
  window.refreshDirty('modal-edit');
  assertEqual(s.state.dirty, false, 'refreshDirty: reverting clean');
  assertEqual(window.refreshDirty('nonexistent'), undefined, 'refreshDirty: unknown id no-op');
})();

// ── markDirtyModal: forced dirty for non-field changes (attachments) ──
(function () {
  var s = setup();
  assertEqual(s.state.dirty, false, 'markDirtyModal: clean before');
  window.markDirtyModal('modal-edit');
  assertEqual(s.state.dirty, true, 'markDirtyModal: forced dirty');
  assertEqual(window._dirtyChecks['modal-edit'].isDirty(), true, 'markDirtyModal: registered check is dirty');
  window.captureDirty('modal-edit');
  assertEqual(s.state.dirty, false, 'markDirtyModal: capture clears');
  assertEqual(window.markDirtyModal('nonexistent'), undefined, 'markDirtyModal: unknown id no-op');
})();

// ── lazy baseline: fields added after init are baselined on first check ──
(function () {
  var s = setup(['#edit-name', '#edit-desc', '#edit-late']);
  var late = makeEl('input');
  late.id = 'edit-late';
  late.value = 'seed';
  s.form.appendChild(late);
  s.state.markDirty();
  assertEqual(s.state.dirty, false, 'late field: first markDirty baselines it, stays clean');
  late.value = 'changed';
  s.state.markDirty();
  assertEqual(s.state.dirty, true, 'late field: change after baseline: dirty');
})();

// ── untracked fields are exempt from change tracking (greetings) ──
(function () {
  var s = setup();
  var greeting = makeEl('textarea');
  greeting.id = 'edit-greeting';
  greeting.value = '';
  s.form.appendChild(greeting);
  s.state.markDirty();
  assertEqual(s.state.dirty, false, 'untracked greeting textarea: typing does not dirty');
  greeting.value = 'edited greeting';
  s.state.markDirty();
  assertEqual(s.state.dirty, false, 'untracked greeting textarea: edit stays clean');
  window.captureDirty('modal-edit');
  assertEqual(s.state.dirty, false, 'untracked greeting: capture stays clean');
})();

// ── label resolution ──
(function () {
  var s = setup();
  s.nameInput.value = '  My Char  ';
  assertEqual(window._dirtyChecks['modal-edit'].label(), 'My Char', 'label: #id selector, trimmed');
  assertEqual(window._dirtyChecks['modal-edit'].label(), 'My Char', 'label: repeated call consistent');
})();

(function () {
  var s = setup(['#edit-name'], function () { return 'custom label'; });
  assertEqual(window._dirtyChecks['modal-edit'].label(), 'custom label', 'label: function');
})();

(function () {
  var s = setup(['#edit-name'], null);
  assertEqual(window._dirtyChecks['modal-edit'].label(), null, 'label: none -> null');
})();

h.printSummary();
