// Unit tests for delete_mode.js — bulk message delete
var h = require('./_helpers.js');
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

function addMessageToDOM(id) {
  var msg = makeElement('div');
  msg.classList.add('message');
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
  msg.appendChild(delMode);
  messageList.appendChild(msg);
  return msg;
}
addMessageToDOM('msg1');
addMessageToDOM('msg2');
addMessageToDOM('msg3');

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
global.htmx = { ajax: function () {} };
global.customConfirm = function (msg, cb) { cb(true); };
global.alert = function () {};
global._refreshChatList = function () {};

// Load module
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'delete_mode.js'), 'utf8'));

function selectedValues() {
  return Array.from(document.querySelectorAll('.msg-select-checkbox:checked')).map(function (cb) { return cb.value; });
}

// ── enterDeleteMode toggles UI ──
(function () {
  window.enterDeleteMode(null);
  assert(standardInput.classList.contains('hidden'), 'standard-input hidden in delete mode');
  assert(!deleteToolbar.classList.contains('hidden'), 'delete-toolbar visible in delete mode');
})();

// ── exitDeleteMode restores UI ──
(function () {
  window.exitDeleteMode();
  assert(!standardInput.classList.contains('hidden'), 'standard-input visible after exit');
  assert(deleteToolbar.classList.contains('hidden'), 'delete-toolbar hidden after exit');
})();

// ── enterDeleteMode with startMessageId selects range ──
(function () {
  window.enterDeleteMode('msg1');
  var allCbs = document.querySelectorAll('.msg-select-checkbox');
  assert(allCbs[0].checked === true, 'startMessageId range: msg1 checked');
  assert(allCbs[1].checked === true, 'startMessageId range: msg2 checked');
  assert(allCbs[2].checked === true, 'startMessageId range: msg3 checked');
  window.exitDeleteMode();
})();

// ── updateDeleteSelection updates count ──
(function () {
  window.enterDeleteMode(null);
  document.querySelectorAll('.msg-select-checkbox')[0].checked = true;
  document.querySelectorAll('.msg-select-checkbox')[1].checked = true;
  window.updateDeleteSelection();
  assertEqual(Number(deleteCount.textContent), 2, 'count shows 2');
  window.exitDeleteMode();
})();

// ── bulkDeleteSelected with empty selection exits (no fetch) ──
(function () {
  window.enterDeleteMode(null);
  var fetchCalled = false;
  var oldFetch = global.fetch;
  global.fetch = function () { fetchCalled = true; return Promise.resolve({ ok: true }); };
  window.bulkDeleteSelected('chat1');
  assert(!fetchCalled, 'no fetch when no selection');
  global.fetch = oldFetch;
})();

// ── bulkDeleteSelected confirms when selection exists ──
(function () {
  window.enterDeleteMode(null);
  document.querySelectorAll('.msg-select-checkbox')[0].checked = true;
  window.updateDeleteSelection();

  var confirmMsg = null;
  var oldConfirm = global.customConfirm;
  global.customConfirm = function (msg) { confirmMsg = msg; };

  window.bulkDeleteSelected('chat1');
  assert(!!confirmMsg && confirmMsg.indexOf('1') >= 0, 'customConfirm called with count');
  global.customConfirm = oldConfirm;
  window.exitDeleteMode();
})();

// ── normal-mode-actions / delete-mode-checkbox toggles ──
(function () {
  window.enterDeleteMode(null);
  var normalEls = document.querySelectorAll('.normal-mode-actions');
  var delEls = document.querySelectorAll('.delete-mode-checkbox');
  assert(normalEls.length > 0, 'normal-mode-actions exist');
  var allNormalHidden = true;
  for (var i = 0; i < normalEls.length; i++) {
    if (!normalEls[i].classList.contains('hidden')) allNormalHidden = false;
  }
  assert(allNormalHidden, 'normal-mode-actions hidden in delete mode');

  var allDelVisible = true;
  for (var i = 0; i < delEls.length; i++) {
    if (delEls[i].classList.contains('hidden')) allDelVisible = false;
  }
  assert(allDelVisible, 'delete-mode-checkbox visible in delete mode');

  window.exitDeleteMode();
  var normalVisible = true;
  for (var i = 0; i < normalEls.length; i++) {
    if (normalEls[i].classList.contains('hidden')) normalVisible = false;
  }
  assert(normalVisible, 'normal-mode-actions visible after exit');

  var delHidden = true;
  for (var i = 0; i < delEls.length; i++) {
    if (!delEls[i].classList.contains('hidden')) delHidden = false;
  }
  assert(delHidden, 'delete-mode-checkbox hidden after exit');
})();

// ── Result ──
h.printSummary();
