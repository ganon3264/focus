// Tests for the provider key list in providers.js — driven through the verbs the
// form wires up (addProviderKey / actionRemoveProviderKey), asserting the rows
// that end up on screen and the values the form will submit.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;

var path = require('path');
var fs = require('fs');

var PREFIX = 'prov-form';

var doc = h.createMockDocument();

function reg(id, tag) {
  var el = h.makeElement(tag || 'div');
  el.id = id;
  doc._body.appendChild(el);
  return el;
}

var keysInput = reg(PREFIX + '-api-keys', 'input');
keysInput.value = '[]';
var legacyInput = reg('api-key-input-' + PREFIX, 'input');
legacyInput.value = '';
var keyList = reg(PREFIX + '-key-list', 'div');
var keyCount = reg(PREFIX + '-key-count', 'span');

// The row markup the modal ships, so the list renders the real shape.
h.installTemplates(doc, fs.readFileSync(
  path.join(__dirname, '..', '..', 'partials', 'modals', 'provider-create.html'), 'utf8'));

doc.getElementById = function (id) {
  if (id === PREFIX + '-api-keys') return keysInput;
  if (id === 'api-key-input-' + PREFIX) return legacyInput;
  if (id === PREFIX + '-key-list') return keyList;
  if (id === PREFIX + '-key-count') return keyCount;
  return doc._body.querySelector('#' + id);
};

global.window = global;
global.document = doc;
global.StateManager = { get: function () { return null; } };
global.api = {};
global.htmx = { ajax: function () { return Promise.resolve(); } };
global.openModal = function () {};
global.closeModal = function () {};
global.ModalController = { setDirty: function () {} };
global.ProviderStore = { get: function () { return null; }, list: function () { return []; } };
global.PROVIDER_SCHEMA = {};

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'providers.js'), 'utf8'));

// The rows the reader sees, in order.
function rows() {
  return keyList.querySelectorAll('[data-ui="key-row"]');
}

function rowLabels() {
  return rows().map(function (row) {
    var label = row.querySelector('[data-ui="key-row-label"]');
    return label ? label.textContent : null;
  });
}

function submittedKeys() {
  return JSON.parse(keysInput.value);
}

// ── adding a key renders a named row ──
(function () {
  addProviderKey(PREFIX, 'SECRET:alpha');
  assertEqual(rows().length, 1, 'adding a key renders one row');
  assertEqual(rowLabels()[0], 'Saved Key: alpha', 'a saved key is named by its secret');
  assertEqual(keyCount.textContent, '1 key', 'the rail counts one key');
  assertDeepEqual(submittedKeys(), ['SECRET:alpha'], 'the form submits the key ref');
  assertEqual(legacyInput.value, 'SECRET:alpha', 'the first key is mirrored into the legacy field');
})();

// ── adding more keeps the order, a duplicate is a no-op ──
(function () {
  addProviderKey(PREFIX, 'SECRET:beta');
  addProviderKey(PREFIX, 'SECRET:alpha');
  assertDeepEqual(rowLabels(), ['Saved Key: alpha', 'Saved Key: beta'],
    'keys keep the order they were added in, without duplicates');
  assertEqual(rows().length, 2, 'the duplicate does not add a row');
  assertEqual(keyCount.textContent, '2 keys', 'the rail counts both keys');
})();

// ── a raw key is masked in its row ──
(function () {
  addProviderKey(PREFIX, 'sk-raw-value');
  assertEqual(rows().length, 3, 'a raw key renders a row too');
  assertEqual(rowLabels()[2], 'Raw Key (hidden)', 'a raw key is never shown in the list');
  assertEqual(legacyInput.value, 'SECRET:alpha', 'the legacy field still mirrors the first key');
})();

// ── removing a key drops its row and re-mirrors the first key ──
(function () {
  var betaRow = rows()[1];
  window.actionRemoveProviderKey(betaRow.querySelector('[data-ui="key-row-label"]'));
  assertDeepEqual(rowLabels(), ['Saved Key: alpha', 'Raw Key (hidden)'],
    'removing a key drops exactly that row');
  assertDeepEqual(submittedKeys(), ['SECRET:alpha', 'sk-raw-value'], 'the form submits the rest');
  assertEqual(keyCount.textContent, '2 keys', 'the rail follows the removal');
})();

(function () {
  window.actionRemoveProviderKey(rows()[0].querySelector('[data-ui="key-row-label"]'));
  assertDeepEqual(rowLabels(), ['Raw Key (hidden)'], 'the first key can be removed');
  assertEqual(legacyInput.value, 'sk-raw-value', 'the legacy field mirrors the new first key');
})();

// ── emptying the list shows the hint ──
(function () {
  window.actionRemoveProviderKey(rows()[0].querySelector('[data-ui="key-row-label"]'));
  assertEqual(rows().length, 0, 'no rows remain');
  assertDeepEqual(submittedKeys(), [], 'the form submits no keys');
  assertEqual(legacyInput.value, '', 'the legacy field is cleared');
  assertEqual(keyCount.textContent, '0 keys', 'the rail counts zero keys');
  assert(!!keyList.querySelector('.provider-keys-empty'), 'the empty hint is shown');
})();

// ── a key ref the reader types is not duplicated by a second add ──
(function () {
  addProviderKey(PREFIX, 'SECRET:alpha');
  addProviderKey(PREFIX, 'SECRET:alpha');
  assertEqual(rows().length, 1, 're-adding the same ref keeps one row');
})();

h.printSummary();
