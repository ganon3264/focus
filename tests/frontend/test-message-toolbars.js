// Unit tests for refreshMessageToolbars in message-refresh.js.
//
// Extensions only change per-message toolbars; the targeted patch must swap
// each live `.toolbar` in place and skip pruned rows (no live node).
var fs = require('fs');
var path = require('path');
var vm = require('vm');
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var failures = 0;
function check(cond, msg) {
  if (cond) console.log('OK:   ' + msg);
  else { failures++; console.error('FAIL: ' + msg); }
}

function makeToolbar(html) {
  var t = {};
  Object.defineProperty(t, 'outerHTML', {
    get: function () { return t._html; },
    set: function (v) { t._html = v; },
  });
  t._html = html;
  return t;
}

function makeLiveNode(id, toolbarHtml) {
  var toolbar = makeToolbar('<div class="toolbar" data-live="' + id + '">' + toolbarHtml + '</div>');
  return {
    toolbar: toolbar,
    querySelector: function (sel) { return sel === '.toolbar' ? toolbar : null; },
  };
}

function makeWrapper(id, toolbarHtml) {
  var toolbar = { outerHTML: '<div class="toolbar">' + toolbarHtml + '</div>' };
  return {
    dataset: { messageId: id },
    querySelector: function (sel) { return sel === '.toolbar' ? toolbar : null; },
  };
}

function makeSandbox() {
  var live = { '1': makeLiveNode('1', 'old-1'), '3': makeLiveNode('3', 'old-3') };
  // id 2 is pruned: no live node (a placeholder row).
  var wrappers = [
    makeWrapper('1', 'new-1'),
    makeWrapper('2', 'new-2'),
    makeWrapper('3', 'new-3'),
  ];
  var root = { querySelectorAll: function (sel) { return sel === '[data-message-id]' ? wrappers : []; } };
  var parsedDoc = { querySelector: function (sel) { return sel === '.message-toolbars' ? root : null; } };

  var reapplyCalls = 0;
  var processed = [];
  var sandbox = {
    console: console,
    document: h.createMockDocument(),
    DOMParser: function () { this.parseFromString = function () { return parsedDoc; }; },
    hxFetch: function (url) {
      sandbox._fetched = url;
      return Promise.resolve({ ok: true, text: function () { return Promise.resolve('<html/>'); } });
    },
    StateManager: { get: function () { return null; } },
    reapplyDeleteMode: function () { reapplyCalls++; },
    htmx: { process: function (node) { processed.push(node); } },
    _reapplyCalls: function () { return reapplyCalls; },
    _processed: processed,
    _live: live,
  };
  sandbox.window = sandbox;
  sandbox.addEventListener = function () {};
  sandbox.removeEventListener = function () {};
  sandbox.window.api = { partials: { messageToolbars: function (id) { return '/partials/message-toolbars/' + id; } } };
  sandbox.document.getElementById = function (id) { return live[id.replace('message-', '')] || null; };
  vm.createContext(sandbox);
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, '..', '..', 'static/js/messages/message-identity.js'), 'utf8'),
    sandbox,
  );
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, '..', '..', 'static/js/messages/message-refresh.js'), 'utf8'),
    sandbox,
  );
  return sandbox;
}

async function run() {
  var sandbox = makeSandbox();
  await sandbox.window.refreshMessageToolbars('c1');

  assertEqual(sandbox._fetched, '/partials/message-toolbars/c1', 'fetches the toolbars partial');

  var live = sandbox._live;
  assertEqual(live['1'].toolbar.outerHTML, '<div class="toolbar">new-1</div>', 'live toolbar 1 swapped in place');
  assertEqual(live['3'].toolbar.outerHTML, '<div class="toolbar">new-3</div>', 'live toolbar 3 swapped in place');
  check(!live['2'], 'pruned row has no live node');
  assertEqual(sandbox._processed.length, 2, 'htmx re-binds only the swapped (live) nodes');
  assertEqual(sandbox._reapplyCalls(), 1, 'delete mode re-applied after the patch');

  // A failed response is a no-op.
  var sandbox2 = makeSandbox();
  sandbox2.hxFetch = function () { return Promise.resolve({ ok: false }); };
  await sandbox2.window.refreshMessageToolbars('c1');
  assertEqual(sandbox2._live['1'].toolbar.outerHTML, '<div class="toolbar" data-live="1">old-1</div>',
    'failed fetch leaves toolbars untouched');
  assertEqual(sandbox2._reapplyCalls(), 0, 'failed fetch skips delete-mode reapply');

  console.log('\n' + (failures === 0 ? 'all passed' : failures + ' failures'));
  process.exit(failures > 0 ? 1 : 0);
}

run().catch(function (e) {
  console.error('FAIL: threw: ' + (e && e.stack || e));
  process.exit(1);
});
