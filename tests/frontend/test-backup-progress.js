// Unit tests for backup-manager.js — streamed progress for create/clean
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var path = require('path');
var fs = require('fs');

global.window = global;
global.document = h.createMockDocument();
global.fetch = function () {
  return Promise.resolve({ json: function () { return []; }, ok: true });
};
global.window.api = {
  backups: '/api/backups',
  cleanDb: '/api/db/clean',
  chatsStale: '/api/chats/stale',
  backupRestore: function (id) { return '/api/backups/' + id + '/restore'; },
  backupDelete: function (id) { return '/api/backups/' + id; },
};

var toasts = [];
global.showInfoToast = function (msg, opts) { toasts.push({ type: 'info', msg: msg, id: opts && opts.id }); };
global.showSuccessToast = function (msg) { toasts.push({ type: 'success', msg: msg }); };
global.showErrorToast = function (msg) { toasts.push({ type: 'error', msg: msg }); };
global.hideToast = function (id) { toasts.push({ type: 'hide', msg: id }); };

var confirmCallback = null;
global.customConfirm = function (msg, cb) { confirmCallback = cb; };

var runResolve = null;
var emit = null;
global.streamProgress = function (url, opts, onEvent) {
  global._progressUrl = url;
  emit = onEvent;
  return new Promise(function (resolve) {
    runResolve = resolve;
  });
};

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'features', 'backup-manager.js'), 'utf8'));

var BM = window.BackupManager;
assert(!!BM, 'BackupManager loaded');

var btn = global.document.createElement('button');
btn.id = 'btn-create-backup';
global.document.body.appendChild(btn);

// ── create: live progress in one toast, success on completion ──
var created = BM.create();
assertEqual(global._progressUrl, '/api/backups', 'create: posts to the backups endpoint');
assertEqual(btn.disabled, true, 'create: button disabled while running');
assertEqual(toasts[0].msg, 'Creating backup…', 'create: opens a live toast');
assertEqual(toasts[0].id, 'backup-create', 'create: live toast is id-keyed');

emit({ type: 'progress', label: 'Reading database' });
assertEqual(toasts[1].msg, 'Creating backup — Reading database', 'create: stage label shown');

emit({ type: 'progress', label: 'Archiving files', current: 2, total: 5 });
assertEqual(
  toasts[2].msg,
  'Creating backup — Archiving files 2/5',
  'create: counts shown when the stage has them',
);

runResolve({ id: 'b1', size_bytes: 2048 });

created.then(function () {
  assertEqual(toasts[3].type, 'hide', 'create: live toast hidden on completion');
  assertEqual(toasts[3].msg, 'backup-create', 'create: hides by id');
  assertEqual(toasts[4].msg, 'Backup created (2.0 KB)', 'create: success toast carries the size');
  assertEqual(btn.disabled, false, 'create: button re-enabled');

  // ── create: failures surface, button still recovers ──
  toasts.length = 0;
  global.streamProgress = function () {
    return Promise.reject(new Error('disk full'));
  };
  return BM.create().then(function () {
    assertEqual(toasts[0].msg, 'Creating backup…', 'create failure: live toast still opens');
    assertEqual(toasts[1].type, 'hide', 'create failure: live toast hidden');
    assertEqual(toasts[2].msg, 'Backup failed: disk full', 'create failure: error toast');
    assertEqual(btn.disabled, false, 'create failure: button re-enabled');

    // ── clean: confirm, stream stages, report counts ──
    toasts.length = 0;
    var cleanCalls = 0;
    global.streamProgress = function (url, opts, onEvent) {
      cleanCalls++;
      global._progressUrl = url;
      emit = onEvent;
      return new Promise(function (resolve) {
        runResolve = resolve;
      });
    };
    var cleanBtn = { disabled: false };
    BM.cleanDatabase(cleanBtn);
    assert(typeof confirmCallback === 'function', 'clean: asks for confirmation first');
    assertEqual(cleanCalls, 0, 'clean: nothing runs before the confirm');

    confirmCallback();
    assertEqual(global._progressUrl, '/api/db/clean', 'clean: posts to the clean endpoint');
    assertEqual(cleanBtn.disabled, true, 'clean: button disabled while running');
    assertEqual(toasts[0].msg, 'Cleaning database…', 'clean: opens a live toast');

    emit({ type: 'progress', label: 'Trashed chats' });
    assertEqual(toasts[1].msg, 'Cleaning — Trashed chats', 'clean: stage label shown');

    runResolve({ chats: 3, characters: 0, orphaned_files: 12, empty_dirs_removed: 0 });
    return new Promise(function (resolve) {
      setTimeout(resolve, 0);
    }).then(function () {
      assertEqual(toasts[2].msg, 'clean-db', 'clean: live toast hidden');
      assertEqual(
        toasts[3].msg,
        'Database cleaned: 3 chats deleted, 12 orphaned files',
        'clean: zero counts dropped from the summary',
      );
      assertEqual(cleanBtn.disabled, false, 'clean: button re-enabled');
      h.printSummary();
    });
  });
});
