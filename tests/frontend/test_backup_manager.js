// Unit tests for backup_manager.js — export state machine
var failures = 0, tests = 0;

function assert(cond, msg) { tests++; if (!cond) { console.error('FAIL: ' + msg); failures++; } else console.log('OK:   ' + msg); }
function assertEqual(a, b, msg) { tests++; if (a !== b) { console.error('FAIL: ' + msg + ' — expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a)); failures++; } else console.log('OK:   ' + msg); }
function assertDeepEqual(a, b, msg) { var s = JSON.stringify(a), t = JSON.stringify(b); tests++; if (s !== t) { console.error('FAIL: ' + msg + ' — expected ' + t + ', got ' + s); failures++; } else console.log('OK:   ' + msg); }

var path = require('path');
var fs = require('fs');

// Mock browser APIs
global.window = global;
global.document = {
  getElementById: function() { return null; },
  querySelector: function() { return null; },
  querySelectorAll: function() { return []; }
};
global.openModal = function() {};
global.closeModal = function() {};
global.htmx = { ajax: function() { return Promise.resolve(); } };
global.fetch = function(url, opts) {
  global._lastFetch = { url: url, opts: opts };
  return Promise.resolve({ json: function() { return []; }, ok: true, blob: function() { return Promise.resolve(new Blob()); } });
};
global.window.api = {
  backups: '/api/backups',
  export: '/api/export',
  cleanDb: '/api/db/clean',
  chats: '/api/chats',
  import_: '/api/import',
  backupRestore: function(id) { return '/api/backups/' + id + '/restore'; },
  backupDelete: function(id) { return '/api/backups/' + id; },
  partials: {
    exportEntities: '/partials/export-entities',
  },
};
global.URL = { createObjectURL: function() { return 'blob:url'; }, revokeObjectURL: function() {} };
global.Blob = function() {};

// Load module
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'features', 'backup_manager.js'), 'utf8'));

var BM = window.BackupManager;
assert(!!BM, 'BackupManager loaded');

// ── Initial export state ──
(function() {
  var s = BM._exportState;
  assertEqual(s.characters, 'none', 'initial: characters = none');
  assertEqual(s.personas, 'none', 'initial: personas = none');
  assertEqual(s.presets, 'none', 'initial: presets = none');
  assertEqual(s.chats, false, 'initial: chats = false');
  assertEqual(s.providers, false, 'initial: providers = false');
  assertEqual(s.secrets, false, 'initial: secrets = false');
  assertDeepEqual(s.selCharacters, {}, 'initial: selCharacters empty');
  assertDeepEqual(s.selPersonas, {}, 'initial: selPersonas empty');
  assertDeepEqual(s.selPresets, {}, 'initial: selPresets empty');
})();

// ── setExportType 'all' ──
(function() {
  BM.openExportModal();  // resets state
  BM.setExportType('characters', 'all');
  assertEqual(BM._exportState.characters, 'all', 'setExportType(all): characters = all');
  assertDeepEqual(BM._exportState.selCharacters, {}, 'setExportType(all): selCharacters cleared');
})();

// ── setExportType 'none' ──
(function() {
  BM.openExportModal();
  BM.setExportType('characters', 'all');
  BM.setExportType('characters', 'none');
  assertEqual(BM._exportState.characters, 'none', 'setExportType(none): characters = none');
})();

// ── toggleExportFlag toggles booleans ──
(function() {
  BM.openExportModal();
  assertEqual(BM._exportState.chats, false, 'toggleExportFlag: chats starts false');
  BM.toggleExportFlag('chats');
  assertEqual(BM._exportState.chats, true, 'toggleExportFlag: chats toggled to true');
  BM.toggleExportFlag('chats');
  assertEqual(BM._exportState.chats, false, 'toggleExportFlag: chats toggled back to false');
  BM.toggleExportFlag('providers');
  assertEqual(BM._exportState.providers, true, 'toggleExportFlag: providers toggled to true');
  BM.toggleExportFlag('secrets');
  assertEqual(BM._exportState.secrets, true, 'toggleExportFlag: secrets toggled to true');
})();

// ── toggleExportEntity adds/removes from selection ──
(function() {
  BM.openExportModal();
  // After openExportModal, characters=none, selChars={}
  BM.setExportType('characters', 'some');
  // After setExportType('some'), characters='some'
  assertDeepEqual(BM._exportState.selCharacters, {}, 'selCharacters empty before toggle');

  var el = { dataset: { exportId: 'char1' }, querySelector: function() { return { checked: false }; } };
  BM.toggleExportEntity(el, 'characters', 'char1');
  assertEqual(BM._exportState.selCharacters.char1, true, 'toggleExportEntity: char1 selected');

  BM.toggleExportEntity(el, 'characters', 'char1');
  assertEqual(BM._exportState.selCharacters.char1, undefined, 'toggleExportEntity: char1 deselected');
})();

// ── doExport builds correct body for 'all' mode ──
(function() {
  BM.openExportModal();
  BM.setExportType('characters', 'all');
  BM.setExportType('personas', 'all');
  BM.setExportType('presets', 'all');
  BM.toggleExportFlag('providers');
  BM.toggleExportFlag('secrets');

  var lastBody = null;
  global._lastFetch = null;
  global.fetch = function(url, opts) {
    if (url === '/api/chats/') return Promise.resolve({ json: function() { return []; }, ok: true });
    global._lastFetch = { url: url, opts: opts };
    lastBody = JSON.parse(opts.body);
    return Promise.resolve({ blob: function() { return Promise.resolve(new Blob()); }, ok: true });
  };

  return BM.doExport().then(function() {
    assert(!!lastBody, 'doExport: fetch called');
    assertDeepEqual(lastBody.characters, ['*'], 'doExport: characters = ["*"]');
    assertDeepEqual(lastBody.personas, ['*'], 'doExport: personas = ["*"]');
    assertDeepEqual(lastBody.presets, ['*'], 'doExport: presets = ["*"]');
    assertDeepEqual(lastBody.chats, [], 'doExport: chats = []');
    assertEqual(lastBody.include_providers, true, 'doExport: include_providers = true');
    assertEqual(lastBody.include_secrets, true, 'doExport: include_secrets = true');
  });
})();

// ── doExport builds correct body for 'some' mode ──
(function() {
  BM.openExportModal();
  BM.setExportType('characters', 'some');
  BM._exportState.selCharacters = { char1: true, char2: true };
  BM.setExportType('personas', 'none');
  BM.setExportType('presets', 'none');
  BM.toggleExportFlag('chats');

  var lastBody = null;
  global.fetch = function(url, opts) {
    if (url === '/api/chats/') return Promise.resolve({ json: function() { return []; }, ok: true });
    lastBody = JSON.parse(opts.body);
    return Promise.resolve({ blob: function() { return Promise.resolve(new Blob()); }, ok: true });
  };

  return BM.doExport().then(function() {
    assertDeepEqual(lastBody.characters, ['char1', 'char2'], 'doExport some: characters = selected ids');
    assertDeepEqual(lastBody.personas, [], 'doExport some: personas = []');
    assertDeepEqual(lastBody.presets, [], 'doExport some: presets = []');
    assertEqual(lastBody.include_providers, false, 'doExport some: include_providers = false');
  });
})();

// ── doExport filters chats by selected characters ──
(function() {
  BM.openExportModal();
  BM.setExportType('characters', 'some');
  BM._exportState.selChars = { char1: true };
  BM.toggleExportFlag('chats');

  var lastBody = null;
  global.fetch = function(url, opts) {
    if (url === '/api/chats/') {
      return Promise.resolve({ json: function() { return [{ id: 'chat1', character_id: 'char1' }, { id: 'chat2', character_id: 'char2' }]; }, ok: true });
    }
    lastBody = JSON.parse(opts.body);
    return Promise.resolve({ blob: function() { return Promise.resolve(new Blob()); }, ok: true });
  };

  return BM.doExport().then(function() {
    assertDeepEqual(lastBody.chats, ['chat1'], 'doExport chat filter: only char1 chats');
  });
})();

// ── Result ──
console.log('\n' + tests + ' tests, ' + failures + ' failures');
process.exit(failures > 0 ? 1 : 0);
