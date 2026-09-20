// Unit tests for the provider key-list helpers in providers.js.
//
// Only the hidden inputs are needed: the render/sortable paths bail out when
// their container element is absent, so they are exercised only in the browser.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;

var path = require('path');
var fs = require('fs');

var inputs = {
  'prov-form-api-keys': { value: '[]' },
  'api-key-input-prov-form': { value: '' },
};

global.window = global;
global.document = {
  getElementById: function (id) { return inputs[id] || null; },
  createElement: function () { return {}; },
};
global.StateManager = { get: function () { return null; } };
global.api = {};
global.htmx = { ajax: function () { return Promise.resolve(); } };
global.openModal = function () {};
global.closeModal = function () {};

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'providers.js'), 'utf8'));

// ── _getProviderKeys parses and filters ──
inputs['prov-form-api-keys'].value = JSON.stringify(['SECRET:a', 'SECRET:b']);
assertDeepEqual(_getProviderKeys('prov-form'), ['SECRET:a', 'SECRET:b'], 'keys parsed in order');

inputs['prov-form-api-keys'].value = 'not json';
assertDeepEqual(_getProviderKeys('prov-form'), [], 'malformed json yields no keys');

inputs['prov-form-api-keys'].value = JSON.stringify(['SECRET:a', '', 5]);
assertDeepEqual(_getProviderKeys('prov-form'), ['SECRET:a'], 'empty/non-string entries dropped');

// ── addProviderKey appends, dedupes, mirrors the first key ──
inputs['prov-form-api-keys'].value = '[]';
addProviderKey('prov-form', 'SECRET:a');
addProviderKey('prov-form', 'SECRET:b');
addProviderKey('prov-form', 'SECRET:a');
assertDeepEqual(_getProviderKeys('prov-form'), ['SECRET:a', 'SECRET:b'], 'add dedupes and preserves order');
assertEqual(inputs['api-key-input-prov-form'].value, 'SECRET:a', 'first key mirrored into the legacy api_key input');

// ── actionRemoveProviderKey drops the row's ref ──
var row = { dataset: { prefix: 'prov-form', ref: 'SECRET:a' }, closest: function () { return this; } };
window.actionRemoveProviderKey(row);
assertDeepEqual(_getProviderKeys('prov-form'), ['SECRET:b'], 'remove drops the matching key');
assertEqual(inputs['api-key-input-prov-form'].value, 'SECRET:b', 'legacy mirror follows the new first key');

// ── labels ──
assertEqual(_keyRowLabel('SECRET:my-key'), 'Saved Key: my-key', 'saved key label');
assertEqual(_keyRowLabel('sk-raw'), 'Raw Key (hidden)', 'raw key label');

h.printSummary();
