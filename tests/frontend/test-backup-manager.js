// Tests for backup-manager.js — what the export and purge flows send and what
// they leave on screen.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual,
  assertIncludes = h.assertIncludes;

var path = require('path');
var fs = require('fs');

// ── DOM ──
var doc = h.createMockDocument();
var byId = {};

function reg(id, tag) {
  var el = h.makeElement(tag || 'div');
  el.id = id;
  el.style = {};
  doc._body.appendChild(el);
  byId[id] = el;
  return el;
}

['export-download-btn', 'export-toggle-chats', 'export-toggle-providers', 'export-toggle-secrets',
  'purge-old-chats-status', 'btn-purge-old-chats', 'purge-days-custom'].forEach(function (id) {
  reg(id, id === 'purge-days-custom' ? 'input' : 'button');
});

['characters', 'personas', 'presets'].forEach(function (type) {
  ['none', 'all', 'some'].forEach(function (val) {
    var b = h.makeElement('button');
    b.setAttribute('data-export-btn', type);
    b.dataset.exportVal = val;
    b.textContent = val;
    doc._body.appendChild(b);
  });
});

doc.getElementById = function (id) { return byId[id] || null; };
var baseCreate = doc.createElement;
var anchors = [];
doc.createElement = function (tag) {
  var el = baseCreate(tag);
  if (tag === 'a') {
    anchors.push(el);
    el.click = function () { el._clicked = true; };
  }
  return el;
};
doc.body = doc._body;
doc.body.removeChild = function (el) { el.remove(); };

function exportBtn(type, val) {
  return doc.querySelectorAll('[data-export-btn="' + type + '"]').filter(function (b) {
    return b.dataset.exportVal === val;
  })[0];
}

function isActive(id) {
  return doc.getElementById(id).classList.contains('active');
}

// ── browser globals ──
var toasts = [];
var confirms = [];
var openedModals = [];
var closedModals = [];

global.window = global;
global.document = doc;
global.openModal = function (id) { openedModals.push(id); };
global.closeModal = function (id) { closedModals.push(id); };
global.showSuccessToast = function (msg) { toasts.push({ type: 'success', msg: msg }); };
global.showErrorToast = function (msg) { toasts.push({ type: 'error', msg: msg }); };
global.showInfoToast = function (msg) { toasts.push({ type: 'info', msg: msg }); };
global.hideToast = function () {};
global.streamProgress = function () { return Promise.resolve({ size_bytes: 1024 }); };
global.customConfirm = function (msg, cb) { confirms.push({ msg: msg, cb: cb }); };
global.htmx = { ajax: function () { return Promise.resolve(); } };
global.URL = { createObjectURL: function () { return 'blob:url'; }, revokeObjectURL: function () {} };
global.Blob = function () {};
global.window.api = {
  backups: '/api/backups',
  export: '/api/export',
  cleanDb: '/api/db/clean',
  chats: '/api/chats',
  chatsStale: '/api/chats/stale',
  import_: '/api/import',
  backupRestore: function (id) { return '/api/backups/' + id + '/restore'; },
  backupDelete: function (id) { return '/api/backups/' + id; },
  partials: { exportEntities: '/partials/export-entities' },
};

var calls = [];
var staleCount = 0;
var chatRows = [];
global.fetch = function (url, opts) {
  calls.push({ url: url, opts: opts || {} });
  if (url.indexOf('/api/chats/stale') === 0) {
    if (opts && opts.method === 'DELETE') {
      return Promise.resolve({
        ok: true,
        json: function () { return { count: staleCount, deleted: staleCount, ids: [] }; },
      });
    }
    return Promise.resolve({ ok: true, json: function () { return { count: staleCount }; } });
  }
  if (url === '/api/chats') {
    return Promise.resolve({ ok: true, json: function () { return chatRows; } });
  }
  return Promise.resolve({
    ok: true,
    json: function () { return {}; },
    blob: function () { return Promise.resolve(new Blob()); },
  });
};

h.installRequestPrimitives(global);

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'features', 'backup-manager.js'), 'utf8'));

var BM = window.BackupManager;
assert(!!BM, 'BackupManager loaded');

function tick() {
  return new Promise(function (r) { setImmediate(r); });
}

function findCall(pred) {
  for (var i = calls.length - 1; i >= 0; i--) if (pred(calls[i])) return calls[i];
  return null;
}

function exportCall() {
  return findCall(function (c) { return c.url === '/api/export'; });
}

function exportBody() {
  var c = exportCall();
  return c ? JSON.parse(c.opts.body) : null;
}

function exportRow(id) {
  var row = h.makeElement('div');
  row.dataset.exportId = id;
  var cb = h.makeElement('input');
  cb.setAttribute('type', 'checkbox');
  row.appendChild(cb);
  row._checkbox = cb;
  return row;
}

function reset() {
  calls.length = 0;
  toasts.length = 0;
  confirms.length = 0;
  closedModals.length = 0;
  anchors.length = 0;
  staleCount = 0;
  chatRows = [];
}

// ── the export request carries the chosen scope ──
async function exportsEverything() {
  reset();
  BM.openExportModal();
  assertEqual(openedModals[openedModals.length - 1], 'modal-export', 'the export modal opens');
  assert(!isActive('export-toggle-chats'), 'chats start unselected');
  assert(!exportBtn('characters', 'all').classList.contains('active'), 'characters start unselected');

  BM.setExportType('characters', 'all');
  BM.setExportType('personas', 'all');
  BM.setExportType('presets', 'all');
  BM.toggleExportFlag('providers');
  BM.toggleExportFlag('secrets');
  assert(exportBtn('characters', 'all').classList.contains('active'), 'the all button shows as active');
  assert(isActive('export-toggle-providers'), 'the providers toggle shows as active');

  await BM.doExport();
  await tick();

  var call = exportCall();
  assert(!!call, 'the export posts to the export endpoint');
  assertEqual(call.url, '/api/export', 'export goes to /api/export');
  var body = exportBody();
  assertDeepEqual(body.characters, ['*'], 'characters = ["*"]');
  assertDeepEqual(body.personas, ['*'], 'personas = ["*"]');
  assertDeepEqual(body.presets, ['*'], 'presets = ["*"]');
  assertDeepEqual(body.chats, [], 'chats = [] while the flag is off');
  assertEqual(body.include_providers, true, 'include_providers = true');
  assertEqual(body.include_secrets, true, 'include_secrets = true');

  assertEqual(anchors.length, 1, 'the blob is handed to a download anchor');
  assertEqual(anchors[0].download, 'focus-export.focus', 'the download is named');
  assert(anchors[0]._clicked, 'the download is triggered');
  assertEqual(closedModals[closedModals.length - 1], 'modal-export', 'the modal closes');
  assertEqual(toasts[toasts.length - 1].type, 'success', 'the reader is told the export is ready');
  assertEqual(doc.getElementById('export-download-btn').textContent, 'Export', 'the button is restored');
  assertEqual(doc.getElementById('export-download-btn').disabled, false, 'the button is re-enabled');
}

// ── picking entities shows up in the request ──
async function exportsSelection() {
  reset();
  BM.openExportModal();
  BM.setExportType('characters', 'some');
  var row1 = exportRow('char1');
  var row2 = exportRow('char2');
  BM.toggleExportEntity(row1, 'characters', 'char1');
  BM.toggleExportEntity(row2, 'characters', 'char2');
  assert(row1._checkbox.checked, 'the picked row shows as checked');
  assertEqual(exportBtn('characters', 'some').textContent, 'Selected (2)',
    'the Select button carries the count');

  BM.toggleExportEntity(row2, 'characters', 'char2');
  assert(!row2._checkbox.checked, 'unpicking the row unchecks it');
  assertEqual(exportBtn('characters', 'some').textContent, 'Selected (1)',
    'the count follows the selection');
  BM.toggleExportEntity(row2, 'characters', 'char2');
  BM.setExportType('personas', 'none');
  BM.setExportType('presets', 'none');

  await BM.doExport();
  await tick();

  var body = exportBody();
  assertDeepEqual(body.characters, ['char1', 'char2'], 'characters = the selected ids');
  assertDeepEqual(body.personas, [], 'personas = [] when set to none');
  assertDeepEqual(body.presets, [], 'presets = [] when set to none');
  assertEqual(body.include_providers, false, 'include_providers = false');
  assertEqual(body.include_secrets, false, 'include_secrets = false');
}

// ── toggling a flag back off is what the request says ──
async function exportsNothing() {
  reset();
  BM.openExportModal();
  BM.setExportType('characters', 'all');
  BM.setExportType('characters', 'none');
  BM.toggleExportFlag('providers');
  BM.toggleExportFlag('providers');
  assert(!isActive('export-toggle-providers'), 'toggling twice leaves the toggle off');
  assert(!exportBtn('characters', 'all').classList.contains('active'),
    'switching back to none deactivates the all button');

  await BM.doExport();
  await tick();

  var body = exportBody();
  assertDeepEqual(body.characters, [], 'characters = []');
  assertEqual(body.include_providers, false, 'include_providers = false');
}

// ── the chats flag sends the chat ids ──
async function exportsChats() {
  reset();
  chatRows = [
    { id: 'chat1', character_id: 'char1' },
    { id: 'chat2', character_id: 'char2' },
  ];
  BM.openExportModal();
  BM.setExportType('characters', 'all');
  BM.toggleExportFlag('chats');
  assert(isActive('export-toggle-chats'), 'the chats toggle shows as active');

  await BM.doExport();
  await tick();

  assertDeepEqual(exportBody().chats, ['chat1', 'chat2'], 'every chat id travels with the export');
}

// ── a picked character narrows the chats to that character's ──
async function exportsChatsForPickedCharacters() {
  reset();
  chatRows = [
    { id: 'chat1', character_id: 'char1' },
    { id: 'chat2', character_id: 'char2' },
  ];
  var list = reg('entity-select-list');
  list.children.length = 0;
  var row = h.makeElement('div');
  row.setAttribute('data-export-id', 'char1');
  var cb = h.makeElement('input');
  cb.type = 'checkbox';
  row.appendChild(cb);
  list.appendChild(row);

  BM.openExportModal();
  BM.setExportType('characters', 'some');
  BM.toggleExportEntity(row, 'characters', 'char1');
  BM.toggleExportFlag('chats');

  await BM.doExport();
  await tick();

  assertDeepEqual(exportBody().characters, ['char1'], 'only the picked character is exported');
  assertDeepEqual(exportBody().chats, ['chat1'], 'chats are narrowed to the picked character');
}

// ── the purge preview counts through the range the reader picked ──
async function purgePreviewFollowsRange() {
  reset();
  staleCount = 3;
  BM.setPurgeRange({ value: '180' });
  await tick();

  var preview = findCall(function (c) { return c.url.indexOf('/api/chats/stale') === 0; });
  assertEqual(preview.url, '/api/chats/stale?days=180', 'the preview asks for the chosen range');
  assertEqual(doc.getElementById('purge-old-chats-status').textContent,
    '3 chats older than 180 days', 'the status reads the count back');
  assertEqual(doc.getElementById('btn-purge-old-chats').disabled, false,
    'the purge button is enabled when there are old chats');

  BM.setPurgeCustom({ value: '45' });
  await tick();
  preview = findCall(function (c) { return c.url.indexOf('/api/chats/stale') === 0; });
  assertEqual(preview.url, '/api/chats/stale?days=45', 'the custom day count drives the preview');

  staleCount = 0;
  BM.setPurgeRange({ value: '90' });
  await tick();
  assertEqual(doc.getElementById('purge-old-chats-status').textContent,
    'No chats older than 90 days.', 'an empty count is reported');
  assertEqual(doc.getElementById('btn-purge-old-chats').disabled, true,
    'the purge button is disabled with nothing to purge');
}

// ── the purge refuses a range under a day ──
async function purgeRefusesEmptyRange() {
  reset();
  BM.setPurgeRange({ value: '0' });
  await tick();
  assertEqual(doc.getElementById('purge-old-chats-status').textContent, 'Enter at least 1 day.',
    'the status asks for a real range');
  assertEqual(doc.getElementById('btn-purge-old-chats').disabled, true, 'the purge button is disabled');

  BM.purgeOldChats();
  await tick();
  assertEqual(confirms.length, 0, 'nothing is confirmed');
  assertEqual(calls.filter(function (c) { return c.opts.method === 'DELETE'; }).length, 0,
    'no delete is sent');
}

// ── the purge confirms with the previewed count, then deletes ──
async function purgeDeletesAfterConfirm() {
  reset();
  staleCount = 3;
  BM.setPurgeRange({ value: '180' });
  await tick();

  BM.purgeOldChats();
  assertEqual(confirms.length, 1, 'the reader is asked to confirm');
  assertIncludes(confirms[0].msg, '3 chats', 'the confirmation shows the previewed count');
  assertIncludes(confirms[0].msg, '180 days', 'the confirmation names the range');

  confirms[0].cb();
  await tick();

  var del = findCall(function (c) { return c.opts.method === 'DELETE'; });
  assert(!!del, 'confirming sends a delete');
  assertEqual(del.url, '/api/chats/stale?days=180', 'the delete targets the previewed range');
  assertEqual(toasts[toasts.length - 1].msg, '3 chats moved to Trash', 'the reader is told what moved');
  assertEqual(toasts[toasts.length - 1].type, 'success', 'the report is a success');
}

// ── Result ──
(async function () {
  var steps = [
    exportsEverything,
    exportsSelection,
    exportsNothing,
    exportsChats,
    exportsChatsForPickedCharacters,
    purgePreviewFollowsRange,
    purgeRefusesEmptyRange,
    purgeDeletesAfterConfirm,
  ];
  for (var i = 0; i < steps.length; i++) {
    try {
      await steps[i]();
    } catch (e) {
      assert(false, steps[i].name + ' threw: ' + e.message);
    }
  }
  h.printSummary();
})();
