// Unit tests for dirty-state.js — modal dirty tracking + HTMX swap handling
var h = require('./helpers.js');
var assert = h.assert;
var assertEqual = h.assertEqual;
var makeElement = h.makeElement;

function createMockMutationObserver() {
  var instances = [];
  var Ctor = function (callback) {
    this._callback = callback;
    this._target = null;
    instances.push(this);
  };
  Ctor.prototype.observe = function (target) { this._target = target; };
  Ctor.prototype.disconnect = function () {};
  Ctor.prototype._add = function (el) {
    this._callback([{ addedNodes: [el], removedNodes: [] }]);
  };
  Ctor._instances = instances;
  return Ctor;
}

var doc = h.createMockDocument();
global.window = global;
global.document = doc;
global.MutationObserver = createMockMutationObserver();

var fs = require('fs');
var path = require('path');
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'dirty-state.js'), 'utf8'));

assert(typeof window.dirtyModalState === 'function', 'dirtyModalState loaded');

function makeEl(tag) {
  var el = makeElement(tag);
  el.nodeType = 1;
  return el;
}

function greetingSection(text, list) {
  var section = makeEl('div');
  var ta = makeEl('textarea');
  ta.id = 'edit-greeting';
  ta.value = text;
  var hidden = makeEl('input');
  hidden.setAttribute('type', 'hidden');
  hidden.setAttribute('name', 'greetings_json');
  hidden.name = 'greetings_json';
  hidden.value = JSON.stringify(list);
  section.appendChild(ta);
  section.appendChild(hidden);
  return section;
}

function setup(initialSection, autoLoad) {
  if (autoLoad === undefined) autoLoad = true;
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
  if (initialSection) form.appendChild(initialSection);
  overlay.appendChild(form);
  doc._body.appendChild(overlay);

  var state = window.dirtyModalState({
    fields: ['#edit-name', '#edit-desc', '#edit-greeting', 'input[name="greetings_json"]'],
    keepBaseline: ['greetings_json'],
    label: '#edit-name',
  });
  state.$el = form;
  var before = MutationObserver._instances.length;
  state.init();
  var observer = MutationObserver._instances[before];

  function swap(section) {
    if (initialSection) initialSection.remove();
    form.appendChild(section);
    initialSection = section;
    observer._add(section);
  }

  if (initialSection && autoLoad) observer._add(initialSection);

  function ta() { return form.querySelector('#edit-greeting'); }

  return { state: state, form: form, nameInput: nameInput, desc: desc, swap: swap, ta: ta };
}

// ── init / typing / revert ──
(function () {
  var s = setup(greetingSection('g0', ['g0']));
  assertEqual(s.state.dirty, false, 'init: clean');
  assertEqual(window._dirtyChecks['modal-edit'].isDirty(), false, 'init: registered check is clean');

  s.nameInput.value = 'New';
  s.state.markDirty();
  assertEqual(s.state.dirty, true, 'typing name: dirty');
  s.nameInput.value = '';
  s.state.markDirty();
  assertEqual(s.state.dirty, false, 'reverting name: clean');

  s.ta().value = 'edited g0';
  s.state.markDirty();
  assertEqual(s.state.dirty, true, 'typing greeting: dirty');
  s.ta().value = 'g0';
  s.state.markDirty();
  assertEqual(s.state.dirty, false, 'reverting greeting: clean');
})();

// ── greeting section swaps (prev/next/add/delete) ──
(function () {
  var s = setup(greetingSection('g0', ['g0']));
  s.ta().value = 'edited g0';
  s.state.markDirty();
  assertEqual(s.state.dirty, true, 'edit: dirty before swipe');

  s.swap(greetingSection('g1', ['edited g0', 'g1']));
  assertEqual(s.state.dirty, true, 'edit + swipe: dirty persists');

  s.swap(greetingSection('g2', ['edited g0', 'g1']));
  assertEqual(s.state.dirty, true, 'second browse swipe: still dirty');

  s.state.markDirty();
  assertEqual(s.state.dirty, true, 'recompute after carry: dirty survives');

  window.captureDirty('modal-edit');
  assertEqual(s.state.dirty, false, 'save (capture): clean');

  s.swap(greetingSection('g1', ['edited g0', 'g1']));
  assertEqual(s.state.dirty, false, 'browse after save: clean');
})();

(function () {
  var s = setup(greetingSection('g0', ['g0']));
  s.swap(greetingSection('g1', ['g0']));
  assertEqual(s.state.dirty, false, 'pure browse: clean');

  s.swap(greetingSection('', ['g0', '']));
  assertEqual(s.state.dirty, true, 'add variant: dirty');

  s.swap(greetingSection('g0', ['g0']));
  assertEqual(s.state.dirty, false, 'delete variant back to original: clean');
})();

(function () {
  var s = setup(null);
  assertEqual(s.state.dirty, false, 'no section yet: clean');
  s.swap(greetingSection('g0', ['g0']));
  assertEqual(s.state.dirty, false, 'first population after open: clean');
})();

// ── async greeting load lands after capture: must stay clean ──
(function () {
  var s = setup(greetingSection('', []), false);
  assertEqual(s.state.dirty, false, 'stale empty section: clean before load');
  s.swap(greetingSection('Hello!', ['Hello!']));
  assertEqual(s.state.dirty, false, 'load lands after capture: clean');
  s.swap(greetingSection('Bye', ['Hello!']));
  assertEqual(s.state.dirty, false, 'browse after load: clean');
  s.ta().value = 'edited';
  s.state.markDirty();
  assertEqual(s.state.dirty, true, 'edit after load: dirty');
  s.swap(greetingSection('Bye', ['edited', 'Hello!']));
  assertEqual(s.state.dirty, true, 'edit + swipe: dirty persists');
})();

h.printSummary();
