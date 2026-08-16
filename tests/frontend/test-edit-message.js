// Unit tests for edit-message.js — message editing (synchronous API)
var h = require('./helpers.js');
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
global.ModalController = { setDirty: function () {} };
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

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'edit-message.js'), 'utf8'));

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

// ── deleteModalAttachment marks the modal dirty via ModalController ──
(function () {
  var marked = false;
  var oldSetDirty = global.ModalController.setDirty;
  global.ModalController.setDirty = function (id, val) {
    assertEqual(id, 'modal-edit-message', 'setDirty: modal id');
    assertEqual(val, true, 'setDirty: true');
    marked = true;
  };
  window.currentEditAttachments = [{ id: 'att1' }];
  window.deleteModalAttachment(0);
  assert(marked, 'setDirty called on attachment delete');
  global.ModalController.setDirty = oldSetDirty;
  window.currentEditAttachments = [];
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

// ── buildEditBlocks prefers segments and preserves tool boundaries ──
(function () {
  var segments = [
    { type: 'text', content: 'before' },
    { type: 'tool_boundary', tool_calls: [{ id: 'c1', function: { name: 'read_file', arguments: '{}' } }] },
    { type: 'reasoning', html: 'think &amp; stuff', index: 1 },
    { type: 'text', content: 'after' },
  ];
  var blocks = window._buildEditBlocks('ignored', segments, 'ignored');
  assertEqual(blocks.length, 4, 'segments path builds all blocks');
  assertEqual(blocks[0].type, 'text', 'first text block');
  assertEqual(blocks[1].type, 'tool_boundary', 'tool boundary preserved');
  assert(blocks[1].calls && blocks[1].calls.length === 1, 'tool calls preserved');
  assertEqual(blocks[2].type, 'reasoning', 'reasoning block preserved');
  assertEqual(blocks[2].content, 'think & stuff', 'reasoning html unescaped');
  assertEqual(blocks[2].index, 1, 'reasoning index preserved');
})();

// ── buildEditBlocks legacy fallback has no marker logic ──
(function () {
  var blocks = window._buildEditBlocks('plain text', null, 'thoughts');
  assertEqual(blocks.length, 2, 'fallback builds reasoning + text');
  assertEqual(blocks[0].type, 'reasoning', 'fallback reasoning first');
  assertEqual(blocks[0].index, 0, 'fallback reasoning is header-controlled');
  assertEqual(blocks[1].content, 'plain text', 'fallback text content');
})();

// ── Result ──
h.printSummary();
