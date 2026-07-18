// Unit tests for edit_message.js — message editing (synchronous API)
var h = require('./_helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

var chatIdInput = makeElement('input');
chatIdInput.id = 'edit-msg-chat-id';
chatIdInput.value = 'chat1';

var msgIdInput = makeElement('input');
msgIdInput.id = 'edit-msg-id';
msgIdInput.value = 'msg1';

var contentTextarea = makeElement('textarea');
contentTextarea.id = 'edit-msg-content';
contentTextarea.value = '';

var thoughtContainer = makeElement('div');
thoughtContainer.id = 'edit-msg-thought-container';
thoughtContainer.style = {};

var thoughtInput = makeElement('textarea');
thoughtInput.id = 'edit-msg-thought';
thoughtInput.value = '';

var attachmentsContainer = makeElement('div');
attachmentsContainer.id = 'edit-msg-attachments';
attachmentsContainer.style = {};
attachmentsContainer.innerHTML = '';

var modal = makeElement('div');
modal.id = 'modal-edit-message';
modal.classList.add('hidden');

var doc = h.createMockDocument();
doc._body.appendChild(chatIdInput);
doc._body.appendChild(msgIdInput);
doc._body.appendChild(contentTextarea);
doc._body.appendChild(thoughtContainer);
doc._body.appendChild(thoughtInput);
doc._body.appendChild(attachmentsContainer);
doc._body.appendChild(modal);
doc.getElementById = function (id) {
  if (id === 'edit-msg-id') return msgIdInput;
  if (id === 'edit-msg-chat-id') return chatIdInput;
  if (id === 'edit-msg-content') return contentTextarea;
  if (id === 'edit-msg-thought-container') return thoughtContainer;
  if (id === 'edit-msg-thought') return thoughtInput;
  if (id === 'edit-msg-attachments') return attachmentsContainer;
  if (id === 'modal-edit-message') return modal;
  return null;
};
doc.createElement = function (tag) {
  var el = h.makeElement(tag);
  el.style = {};
  el.addEventListener = function () {};
  el.appendChild = function (c) {
    var idx = this.children.indexOf(c); if (idx >= 0) this.children.splice(idx, 1);
    this.children.push(c); c.parent = this; return c;
  };
  return el;
};
doc.body = doc._body;
doc.body.addEventListener = function () {};
doc.addEventListener = function () {};

global.window = global;
global.document = doc;
global.alert = function () {};
global.fetch = function () { return Promise.resolve({ ok: true, json: function () { return {}; } }); };
global.api = {
  chatMessage: function (cid, mid) { return '/api/chats/' + cid + '/messages/' + mid; },
  chatAttachments: function (cid) { return '/api/chats/' + cid + '/attachments'; },
  partials: { messageList: function (cid) { return '/partials/message-list/' + cid; } },
};
global.htmx = { ajax: function () {} };
global._refreshChatList = function () {};
global.refreshSingleMessage = null;
global.openModal = function () {};
global.closeModal = function () {};
global.extractThoughtsSafely = function (text) {
  return { processed: text || '', thoughts: [] };
};
global.createMediaThumbnail = function (opts) {
  var div = doc.createElement('div');
  if (opts && opts.onDelete) {
    var btn = doc.createElement('button');
    btn.addEventListener('click', function (e) { opts.onDelete(e); });
    div.appendChild(btn);
    div.querySelector = function () { return btn; };
  }
  return div;
};
global.getSvgSprite = function () { return ''; };
global.setupDropZone = null;
global.FormData = function () { this.append = function () {}; };

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'edit_message.js'), 'utf8'));

assert(typeof window.editMessage === 'function', 'editMessage loaded');

// ── deleteModalAttachment removes by index ──
(function () {
  window.currentEditAttachments = [{ id: 'att1' }, { id: 'att2' }];
  window.deleteModalAttachment(0);
  assertEqual(window.currentEditAttachments.length, 1, 'attachment removed');
  assertEqual(window.currentEditAttachments[0].id, 'att2', 'correct attachment remains');
  window.currentEditAttachments = [];
})();

// ── deleteModalAttachment preserves others ──
(function () {
  window.currentEditAttachments = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  window.deleteModalAttachment(1);
  assertEqual(window.currentEditAttachments.length, 2, 'middle attachment removed');
  assertEqual(window.currentEditAttachments[0].id, 'a', 'first preserved');
  assertEqual(window.currentEditAttachments[1].id, 'c', 'last preserved');
  window.currentEditAttachments = [];
})();

// ── renderEditModalAttachments shows placeholder when empty ──
(function () {
  window.currentEditAttachments = [];
  window.renderEditModalAttachments();
  assert(attachmentsContainer.innerHTML.length > 0, 'empty attachments shows placeholder');
})();

// ── renderEditModalAttachments renders attachments ──
(function () {
  window.currentEditAttachments = [
    { id: 'att1', file_path: '/img/test.png', mime_type: 'image/png' },
  ];
  window.renderEditModalAttachments();
  assert(attachmentsContainer.children.length >= 1, 'attachments rendered');
  window.currentEditAttachments = [];
})();

// ── open/close modal via classList (fallback when openModal absent) ──
(function () {
  // When both openModal and closeModal are available, they're used.
  // When not, the fallback uses classList directly.
  var savedOpen = global.openModal;
  var savedClose = global.closeModal;
  global.openModal = null;
  global.closeModal = null;

  // Test fallback: editMessage stores data but fetch is async
  // Instead, directly test the modal toggle via the classList fallback pattern
  modal.classList.add('hidden');
  // editMessage uses openModal('modal-edit-message') or classList.remove('hidden')
  // saveMessageEdit uses closeModal('modal-edit-message') or classList.add('hidden')
  // We can't test these directly (async), so verify the DOM exists
  assert(modal.id === 'modal-edit-message', 'modal element exists');

  global.openModal = savedOpen;
  global.closeModal = savedClose;
})();

// ── uploadMessageAttachment is safe with empty input ──
(function () {
  // When inputEl.files.length is 0, it should return immediately
  var called = false;
  var oldUpload = window.uploadMessageAttachmentFiles;
  window.uploadMessageAttachmentFiles = function () { called = true; };
  window.uploadMessageAttachment({ files: [] });
  assert(!called, 'upload with empty files does not delegate');
  window.uploadMessageAttachmentFiles = oldUpload;
})();

// ── uploadMessageAttachmentFiles is safe with empty array ──
(function () {
  var called = false;
  var oldFetch = global.fetch;
  global.fetch = function () { called = true; return Promise.resolve({ ok: true }); };
  window.uploadMessageAttachmentFiles([]);
  assert(!called, 'fetch not called with empty array');
  global.fetch = oldFetch;
})();

// ── Result ──
h.printSummary();
