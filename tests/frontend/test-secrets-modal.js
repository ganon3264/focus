// Unit tests for the saved-key library in providers.js — the flows behind the
// banded secrets modal: pick a saved key, paste a raw one, save a named one.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;

var path = require('path');
var fs = require('fs');

var els = {
  'secret-name': { value: '', focus: function () {} },
  'secret-value': { value: '', focus: function () {} },
  'prov-form-api-keys': { value: '[]' },
  'api-key-input-prov-form': { value: '' },
};

global.window = global;
global.document = {
  body: { addEventListener: function () {} },
  getElementById: function (id) { return els[id] || null; },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  createElement: function () { return {}; },
};
global.StateManager = { get: function () { return null; } };
global.api = { partials: {}, providerSecrets: '/api/providers/secrets' };
global.htmx = { ajax: function () { return Promise.resolve(); } };

var closed = [];
var dirty = [];
var toasts = [];
var posts = [];
var changed = [];

global.closeModal = function (id) { closed.push(id); };
global.ModalController = { setDirty: function (id, v) { dirty.push([id, v]); } };
global.showInfoToast = function (m) { toasts.push(m); };
global.showErrorToast = function (m) { toasts.push(m); };
global.Refresh = {
  changed: function () { changed.push([].slice.call(arguments)); return Promise.resolve(); },
  mutate: function () { return Promise.resolve({ ok: true }); },
  load: function () { return Promise.resolve(); },
};
global.hxJson = function (url, method, body) {
  posts.push({ url: url, method: method, body: body });
  return Promise.resolve({ ok: true });
};
global.hxFetch = function () { return Promise.resolve({ ok: true }); };
global.openModal = function () {};
global.escapeHtml = function (s) { return s; };

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'providers.js'), 'utf8'));

function resetKeys() {
  els['prov-form-api-keys'].value = '[]';
  els['api-key-input-prov-form'].value = '';
  els['secret-name'].value = '';
  els['secret-value'].value = '';
  closed = [];
  dirty = [];
  toasts = [];
  posts = [];
  changed = [];
}

function submit() {
  window.actionSubmitSecretForm(
    { reset: function () { els['secret-name'].value = ''; els['secret-value'].value = ''; } },
    { preventDefault: function () {} },
  );
  return new Promise(function (r) { setTimeout(r, 0); });
}

async function main() {
  // ── picking a saved key appends a reference to the provider's list ──
  resetKeys();
  window._currentSecretPrefix = 'prov-form';
  window.actionUseSecret({ dataset: { name: 'openrouter-main' } });
  assertDeepEqual(_getProviderKeys('prov-form'), ['SECRET:openrouter-main'], 'picked key is appended as a reference');
  assertEqual(closed[0], 'modal-secrets', 'picking closes the library');
  assertEqual(dirty.length, 1, 'picking marks the provider form dirty');

  // ── a raw key (no name) goes straight into the list ──
  resetKeys();
  els['secret-value'].value = 'sk-raw';
  await submit();
  assertDeepEqual(_getProviderKeys('prov-form'), ['sk-raw'], 'raw key lands in the provider list');
  assertEqual(posts.length, 0, 'a raw key is not written to the library');
  assertDeepEqual(closed, ['modal-secret-new', 'modal-secrets'], 'adding a raw key closes the form and the library');

  // ── a named key is saved first, then referenced ──
  resetKeys();
  els['secret-name'].value = 'my-key';
  els['secret-value'].value = 'sk-named';
  await submit();
  assertEqual(posts.length, 1, 'a named key is saved to the library');
  assertEqual(posts[0].body.name, 'my-key', 'saved under the typed name');
  assertDeepEqual(_getProviderKeys('prov-form'), ['SECRET:my-key'], 'the saved key is referenced, not inlined');
  assertDeepEqual(closed, ['modal-secret-new', 'modal-secrets'], 'saving from the picker closes the form and the library');

  // ── an empty value is refused ──
  resetKeys();
  els['secret-name'].value = 'my-key';
  await submit();
  assertEqual(posts.length, 0, 'no key without a value');
  assertEqual(toasts.length, 1, 'the empty value is reported');
  assertEqual(closed.length, 0, 'the form stays open');

  // ── manage mode needs a name and refreshes the list ──
  resetKeys();
  window._currentSecretPrefix = null;
  els['secret-value'].value = 'sk-nameless';
  await submit();
  assertEqual(posts.length, 0, 'manage mode refuses an unnamed key');
  assertEqual(toasts.length, 1, 'the missing name is reported');

  resetKeys();
  els['secret-name'].value = 'library-key';
  els['secret-value'].value = 'sk-library';
  await submit();
  assertEqual(posts.length, 1, 'manage mode saves the key');
  assertEqual(changed.length, 1, 'manage mode refreshes the library');
  assertEqual(changed[0][0], 'secrets', 'the secrets resource is invalidated');
  assertDeepEqual(closed, ['modal-secret-new'], 'manage mode closes the form and keeps the library');

  h.printSummary();
}

main();
