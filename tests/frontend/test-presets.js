// Tests for the presets feature module: the one naming dialog that create /
// rename / duplicate share, and the delete fallback.

var h = require('./helpers.js');
var assert = h.assert;
var assertEqual = h.assertEqual;

var path = require('path');
var fs = require('fs');

// ── mocks ──
var els = {
  'preset-name-form': { dataset: { mode: 'new', presetId: '' } },
  'preset-name-input': { value: '', focus: function () {}, select: function () {}, placeholder: '' },
  'preset-name-submit': { textContent: '', className: '' },
};
var titleEl = { textContent: '' };

global.window = global;
global.document = {
  body: { addEventListener: function () {} },
  getElementById: function (id) { return els[id] || null; },
  querySelector: function (sel) { return sel.indexOf('modal-title') !== -1 ? titleEl : null; },
  querySelectorAll: function () { return []; },
  createElement: function () { return {}; },
};
global.api = {
  presets: '/api/presets',
  preset: function (id) { return '/api/presets/' + id; },
  presetDuplicate: function (id) { return '/api/presets/' + id + '/duplicate'; },
  presetImport: '/api/presets/import',
  partials: { presetsModal: '/partials/presets-modal' },
};
global.StateManager = { get: function (key) { return key === 'preset_id' ? 'active-1' : 'chat-1'; } };

var requests = [];
global.hxFetch = function (url, opts) {
  requests.push({ url: url, opts: opts });
  return Promise.resolve({
    ok: true,
    json: function () { return Promise.resolve({ id: 'new-id', name: 'Created' }); },
  });
};

var applied = [];
global.applyPreset = function (id, name) { applied.push({ id: id, name: name }); };
var toasts = [];
global.showSuccessToast = function (m) { toasts.push('ok:' + m); };
global.showErrorToast = function (m) { toasts.push('err:' + m); };
global.openModal = function () {};
global.closeModal = function () {};
global.Refresh = { changed: function () {} };
var confirmMessage = null;
var confirmCallback = null;
global.customConfirm = function (msg, cb) { confirmMessage = msg; confirmCallback = cb; };

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'features', 'presets.js'), 'utf8'));

function flush() { return new Promise(function (r) { setTimeout(r, 0); }); }
function reset() { requests.length = 0; applied.length = 0; toasts.length = 0; }

function submit(mode, presetId, name) {
  els['preset-name-form'].dataset.mode = mode;
  els['preset-name-form'].dataset.presetId = presetId || '';
  els['preset-name-input'].value = name;
  var prevented = false;
  window.actionSubmitPresetName(els['preset-name-form'], { preventDefault: function () { prevented = true; } });
  return prevented;
}

async function main() {
  // ── new: form post, then select what was created ──
  reset();
  assert(submit('new', '', '  My Preset  '), 'new: submit is intercepted');
  await flush();
  assertEqual(requests.length, 1, 'new: one request');
  assertEqual(requests[0].url, '/api/presets', 'new: posts the collection');
  assertEqual(requests[0].opts.method, 'POST', 'new: POST');
  assert(requests[0].opts.body instanceof FormData, 'new: form-encoded body (the endpoint takes Form)');
  assertEqual(requests[0].opts.body.get('name'), 'My Preset', 'new: name is trimmed');
  assertEqual(applied.length, 1, 'new: selects the created preset');
  assertEqual(applied[0].id, 'new-id', 'new: selects the returned id');

  // ── rename: PATCH the row, no selection change ──
  reset();
  submit('rename', 'p1', 'Renamed');
  await flush();
  assertEqual(requests[0].url, '/api/presets/p1', 'rename: patches the preset');
  assertEqual(requests[0].opts.method, 'PATCH', 'rename: PATCH');
  assertEqual(JSON.parse(requests[0].opts.body).name, 'Renamed', 'rename: json body');
  assertEqual(applied.length, 0, 'rename: does not reselect');

  // ── duplicate: POST the duplicate endpoint, then select the copy ──
  reset();
  submit('duplicate', 'p2', 'Copy of Two');
  await flush();
  assertEqual(requests[0].url, '/api/presets/p2/duplicate', 'duplicate: hits the duplicate endpoint');
  assertEqual(requests[0].opts.method, 'POST', 'duplicate: POST');
  assertEqual(applied[0].id, 'new-id', 'duplicate: selects the new row');

  // ── an empty name never reaches the wire ──
  reset();
  submit('new', '', '   ');
  await flush();
  assertEqual(requests.length, 0, 'blank name is rejected before the request');

  // ── a mode that needs an id without one is rejected ──
  reset();
  submit('rename', '', 'Name');
  await flush();
  assertEqual(requests.length, 0, 'rename without an id is rejected');

  // ── delete: confirm first, then remove; active preset falls back to null ──
  reset();
  confirmMessage = null;
  window.actionDeletePreset({
    closest: function () {
      return { dataset: { presetId: 'active-1', presetName: 'Active One' } };
    },
  });
  assert(confirmMessage && confirmMessage.indexOf('Active One') !== -1, 'delete: confirm names the preset');
  assertEqual(requests.length, 0, 'delete: nothing is sent before the confirm resolves');
  confirmCallback();
  await flush();
  assertEqual(requests[0].url, '/api/presets/active-1', 'delete: deletes the row preset');
  assertEqual(requests[0].opts.method, 'DELETE', 'delete: DELETE');
  assertEqual(applied.length, 1, 'delete: the active preset is replaced');
  assertEqual(applied[0].id, null, 'delete: no other row means no preset');

  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
