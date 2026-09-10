// Unit tests for delete-mode.js — bulk message delete with id-based,
// virtualization-safe selection.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

// Build DOM
var standardInput = makeElement('div');
standardInput.id = 'standard-input-container';

var deleteToolbar = makeElement('div');
deleteToolbar.id = 'delete-toolbar';

var deleteCount = makeElement('span');
deleteCount.id = 'delete-selected-count';

var messageList = makeElement('div');
messageList.id = 'message-list';

function makeMessageNode(id) {
  var msg = makeElement('div');
  msg.classList.add('message');
  msg.id = 'message-' + id;
  msg.dataset.messageId = id;
  var cb = makeElement('input');
  cb.type = 'checkbox';
  cb.classList.add('msg-select-checkbox');
  cb.value = id;
  cb.checked = false;
  msg.appendChild(cb);
  var normalMode = makeElement('div');
  normalMode.classList.add('normal-mode-actions');
  msg.appendChild(normalMode);
  var delMode = makeElement('div');
  delMode.classList.add('delete-mode-checkbox');
  delMode.classList.add('hidden');
  msg.appendChild(delMode);
  return msg;
}

function addMessageToDOM(id) {
  var msg = makeMessageNode(id);
  messageList.appendChild(msg);
  return msg;
}
addMessageToDOM('msg1');
addMessageToDOM('msg2');
addMessageToDOM('msg3');

function addPlaceholder(id) {
  var ph = makeElement('div');
  ph.classList.add('message-placeholder');
  ph.dataset.msgId = id;
  messageList.appendChild(ph);
  return ph;
}

var doc = h.createMockDocument();
doc._body.appendChild(standardInput);
doc._body.appendChild(deleteToolbar);
doc._body.appendChild(deleteCount);
doc._body.appendChild(messageList);
doc.body = doc._body;
doc._body.addEventListener = function () {};
doc.body.addEventListener = function () {};
doc.getElementById = function (id) {
  if (id === 'standard-input-container') return standardInput;
  if (id === 'delete-toolbar') return deleteToolbar;
  if (id === 'delete-selected-count') return deleteCount;
  if (id === 'message-list') return messageList;
  return null;
};

global.window = global;
global.document = doc;
global.fetch = function () { return Promise.resolve({ ok: true }); };
global.api = {
  chatBulkDelete: function (id) { return '/api/chats/' + id + '/messages/bulk_delete'; },
  partials: { messageList: function (id) { return '/partials/message-list/' + id; } },
};
global.customConfirm = function (msg, cb) { cb(true); };
global.alert = function () {};
global._refreshChatList = function () {};
global.showSuccessToast = function () {};
global.showErrorToast = function () {};

function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

// Load modules (identity first — delete-mode uses MessageIdentity.bare)
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'message-identity.js'), 'utf8'));
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'delete-mode.js'), 'utf8'));

function messageNode(id) {
  var all = messageList.querySelectorAll('.message');
  for (var i = 0; i < all.length; i++) {
    if (all[i].dataset.messageId === id) return all[i];
  }
  return null;
}
function cbFor(id) {
  var msg = messageNode(id);
  return msg ? msg.querySelector('.msg-select-checkbox') : null;
}

// ── enterDeleteMode toggles UI ──
function enterTogglesUI() {
  window.enterDeleteMode(null);
  assert(standardInput.classList.contains('hidden'), 'standard-input hidden in delete mode');
  assert(!deleteToolbar.classList.contains('hidden'), 'delete-toolbar visible in delete mode');
}

// ── exitDeleteMode restores UI ──
function exitRestoresUI() {
  window.exitDeleteMode();
  assert(!standardInput.classList.contains('hidden'), 'standard-input visible after exit');
  assert(deleteToolbar.classList.contains('hidden'), 'delete-toolbar hidden after exit');
}

// ── enterDeleteMode with startMessageId selects that message and after ──
function rangeScenario() {
  window.enterDeleteMode('msg2');
  assert(!cbFor('msg1').checked, 'range: msg1 (before start) unchecked');
  assert(cbFor('msg2').checked, 'range: msg2 checked');
  assert(cbFor('msg3').checked, 'range: msg3 checked');
  assertEqual(deleteCount.textContent, '2', 'range count is 2');
  window.exitDeleteMode();
}

// ── selection updates incrementally from the changed checkbox ──
function incrementalScenario() {
  window.enterDeleteMode(null);
  var cb1 = cbFor('msg1');
  var cb2 = cbFor('msg2');
  cb1.checked = true;
  window.updateDeleteSelection(cb1);
  cb2.checked = true;
  window.updateDeleteSelection(cb2);
  assertEqual(deleteCount.textContent, '2', 'count reflects two selected');
  cb1.checked = false;
  window.updateDeleteSelection(cb1);
  assertEqual(deleteCount.textContent, '1', 'unchecking removes the id');
  window.exitDeleteMode();
}

// ── entering delete mode does not materialize culled messages ──
function noUnpruneScenario() {
  var ph = addPlaceholder('msg4');
  var unpruneCalls = 0;
  global._unpruneMessage = function () { unpruneCalls++; };

  window.enterDeleteMode(null);
  assert(unpruneCalls === 0, 'enterDeleteMode does not unprune placeholders');
  assert(!!messageList.querySelector('.message-placeholder[data-msg-id="msg4"]'), 'placeholder stays culled');

  window.exitDeleteMode();
  ph.remove();
  delete global._unpruneMessage;
}

// ── range selection spans culled placeholders and repaints on restore ──
function rangeSpansPlaceholdersScenario() {
  var ph = addPlaceholder('msg4');
  window.enterDeleteMode('msg3'); // selects msg3 + msg4 (placeholder)
  assertEqual(deleteCount.textContent, '2', 'range included the culled message');

  var restored = makeMessageNode('msg4');
  window.applyDeleteModeToNode(restored);
  assert(restored.querySelector('.msg-select-checkbox').checked, 'restored selected message is checked');
  assert(!restored.querySelector('.delete-mode-checkbox').classList.contains('hidden'),
    'restored message checkbox is visible');
  assert(restored.querySelector('.normal-mode-actions').classList.contains('hidden'),
    'restored message hides normal actions');

  window.exitDeleteMode();
  ph.remove();
}

// ── applyDeleteModeToNode is a no-op outside delete mode ──
function noopOutsideScenario() {
  var node = makeMessageNode('msg9');
  window.applyDeleteModeToNode(node);
  assert(node.querySelector('.delete-mode-checkbox').classList.contains('hidden'),
    'no delete chrome outside delete mode');
}

// ── bulkDeleteSelected with empty selection exits (no fetch) ──
function emptySelectionScenario() {
  window.enterDeleteMode(null);
  var fetchCalled = false;
  var oldFetch = global.fetch;
  global.fetch = function () { fetchCalled = true; return Promise.resolve({ ok: true }); };
  window.bulkDeleteSelected('chat1');
  assert(!fetchCalled, 'no fetch when no selection');
  global.fetch = oldFetch;
}

// ── bulkDeleteSelected posts the id set ──
async function bulkDeletePostsScenario() {
  window.enterDeleteMode(null);
  var cb = cbFor('msg2');
  cb.checked = true;
  window.updateDeleteSelection(cb);

  var body = null;
  var oldFetch = global.fetch;
  global.fetch = function (url, opts) {
    body = JSON.parse(opts.body);
    return Promise.resolve({ ok: true });
  };

  window.bulkDeleteSelected('chat1');
  await flush();
  assert(body !== null, 'bulk delete posted');
  assertEqual(body.message_ids.join(','), 'msg2', 'posted the selected id');

  global.fetch = oldFetch;
  window.exitDeleteMode();
}

// ── normal-mode-actions / delete-mode-checkbox toggles ──
function chromeTogglesScenario() {
  window.enterDeleteMode(null);
  var normalEls = messageList.querySelectorAll('.normal-mode-actions');
  var delEls = messageList.querySelectorAll('.delete-mode-checkbox');
  var allNormalHidden = normalEls.every(function (el) { return el.classList.contains('hidden'); });
  var allDelVisible = delEls.every(function (el) { return !el.classList.contains('hidden'); });
  assert(allNormalHidden, 'normal-mode-actions hidden in delete mode');
  assert(allDelVisible, 'delete-mode-checkbox visible in delete mode');

  window.exitDeleteMode();
  var normalVisible = normalEls.every(function (el) { return !el.classList.contains('hidden'); });
  var delHidden = delEls.every(function (el) { return el.classList.contains('hidden'); });
  assert(normalVisible, 'normal-mode-actions visible after exit');
  assert(delHidden, 'delete-mode-checkbox hidden after exit');
}

async function main() {
  enterTogglesUI();
  exitRestoresUI();
  rangeScenario();
  incrementalScenario();
  noUnpruneScenario();
  rangeSpansPlaceholdersScenario();
  noopOutsideScenario();
  emptySelectionScenario();
  await bulkDeletePostsScenario();
  chromeTogglesScenario();
  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
