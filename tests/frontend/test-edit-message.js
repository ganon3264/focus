// Tests for edit-message.js — the edit modal and the payload it saves.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;
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

// The empty note is static markup in the template; JS only toggles it.
var attachmentsEmpty = makeElement('span');
attachmentsEmpty.id = 'edit-msg-att-empty';
attachmentsEmpty.classList.add('hidden');

// The block editor's lane: renderEditBlocks fills it, saveMessageEdit reads it.
var blocksContainer = makeElement('div');
blocksContainer.id = 'edit-msg-blocks';

var modal = makeElement('div');
modal.id = 'modal-edit-message';
modal.classList.add('hidden');

var doc = h.createMockDocument();
[chatIdInput, msgIdInput, contentTextarea, thoughtContainer, thoughtInput,
  attachmentsContainer, attachmentsEmpty, blocksContainer, modal].forEach(function (el) {
  doc._body.appendChild(el);
});
doc.getElementById = function (id) {
  if (id === 'edit-msg-id') return msgIdInput;
  if (id === 'edit-msg-chat-id') return chatIdInput;
  if (id === 'edit-msg-content') return contentTextarea;
  if (id === 'edit-msg-thought-container') return thoughtContainer;
  if (id === 'edit-msg-thought') return thoughtInput;
  if (id === 'edit-msg-attachments') return attachmentsContainer;
  if (id === 'edit-msg-att-empty') return attachmentsEmpty;
  if (id === 'edit-msg-blocks') return blocksContainer;
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

var openedModals = [];
var closedModals = [];
var refreshed = [];
var toasts = [];

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
global.refreshSingleMessage = function (cid, mid) { refreshed.push([cid, mid]); };
global.openModal = function (id) { openedModals.push(id); };
global.closeModal = function (id, opts) { closedModals.push({ id: id, opts: opts }); };
global.showErrorToast = function (msg) { toasts.push(msg); };
global.ModalController = { setDirty: function () {} };
global.extractThoughtsSafely = function (text) {
  return { processed: text || '', thoughts: [] };
};
global.openLightbox = function (src) { global._lightboxSrc = src; };
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'media-utils.js'), 'utf8'));
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'utils', 'word-count.js'), 'utf8'));

global.createMediaThumbnail = function (opts) {
  var div = doc.createElement('div');
  div._opts = opts;
  if (opts && opts.onDelete) {
    var btn = doc.createElement('button');
    btn.addEventListener('click', function (e) { opts.onDelete(e); });
    div.appendChild(btn);
    div.querySelector = function () { return btn; };
  }
  return div;
};

// The tool blocks are rendered by the shared card builder; record what the
// editor asks it for, and what it produces, instead of re-deriving the markup.
var cardCalls = [];
global.buildToolCallsSection = function () {
  var el = doc.createElement('div');
  el.className = 'tool-calls';
  return el;
};
global.buildToolCallCard = function (call) {
  cardCalls.push(call);
  var el = doc.createElement('div');
  el.className = 'tool-call-card';
  el.textContent = call.name;
  return el;
};
global.getSvgSprite = function () { return ''; };
global.setupDropZone = null;
global.FormData = function () { this.append = function () {}; };

h.installRequestPrimitives(global);

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'edit-message.js'), 'utf8'));

assert(typeof window.editMessage === 'function', 'editMessage loaded');

var fetchCalls = [];
var messagePayload = {};
global.fetch = function (url, opts) {
  fetchCalls.push({ url: url, opts: opts });
  return Promise.resolve({
    ok: true,
    json: function () { return messagePayload; },
  });
};

// Drives the real open path: fetch the message, build its blocks, render them.
function openEditor(payload) {
  messagePayload = payload;
  fetchCalls.length = 0;
  cardCalls.length = 0;
  return window.editMessage('msg1', 'chat1');
}

function blocks() { return blocksContainer.children; }

function railLabel(section) {
  var rail = section.querySelector('.rail');
  if (!rail) return null;
  for (var i = 0; i < rail.children.length; i++) {
    var c = rail.children[i];
    if (c.tagName === 'SPAN' && !c.dataset.ui) return c.textContent;
  }
  return null;
}

function blockTextarea(section) {
  var ta = section.querySelector('[data-ui="edit-block-ta"]');
  return ta || null;
}

var SEGMENTS = [
  { type: 'text', content: 'before' },
  {
    type: 'tool_boundary',
    tool_calls: [{ id: 'c1', function: { name: 'read_file', arguments: '{}' }, result: 'ok' }],
  },
  { type: 'reasoning', html: 'think &amp; stuff', index: 1 },
  { type: 'text', content: 'after' },
];

// ── the modal renders one editable block per segment, in order ──
async function rendersBlocks() {
  await openEditor({ content: 'ignored', segments: SEGMENTS, reasoning: 'ignored' });

  assertEqual(openedModals[openedModals.length - 1], 'modal-edit-message', 'the editor opens');
  assertEqual(blocks().length, 4, 'one rendered block per segment');
  assertEqual(railLabel(blocks()[0]), 'Text', 'first block is a text block');
  assertEqual(blockTextarea(blocks()[0]).value, 'before', 'text block holds the segment text');
  assertEqual(blocks()[0].querySelector('[data-ui="block-count"]').textContent, '1 word',
    'the block rail reads out its length');

  assert(blocks()[1].classList.contains('msg-block-tool'), 'tool boundary renders a tool block');
  assertEqual(blocks()[1].querySelectorAll('.tool-call-card').length, 1, 'one card per tool call');
  assertEqual(cardCalls.length, 1, 'the shared card builder is used once');
  assertEqual(cardCalls[0].name, 'read_file', 'the card receives the tool name');
  assertEqual(cardCalls[0].result, 'ok', 'the card receives the recorded result');

  assertEqual(railLabel(blocks()[2]), 'Reasoning', 'third block is the reasoning block');
  assertEqual(blockTextarea(blocks()[2]).value, 'think & stuff',
    'reasoning html is decoded for editing');
  assert(blocks()[2].classList.contains('collapsed'), 'reasoning block starts folded');

  assertEqual(railLabel(blocks()[3]), 'Text', 'fourth block is the trailing text');
  assertEqual(blockTextarea(blocks()[3]).value, 'after', 'trailing text is editable');
}

// ── every message gets an editable text block, even without one ──
async function alwaysOffersTextBlock() {
  await openEditor({ content: '', segments: [{ type: 'reasoning', html: 'thought', index: 0 }] });
  assertEqual(blocks().length, 2, 'a reasoning-only message still gets a text block');
  assertEqual(railLabel(blocks()[0]), 'Reasoning', 'reasoning stays first');
  assertEqual(railLabel(blocks()[1]), 'Text', 'text block is appended');
  assertEqual(blockTextarea(blocks()[1]).value, '', 'the text block starts empty');

  await openEditor({ content: 'plain text', segments: null, reasoning: 'thoughts' });
  assertEqual(blocks().length, 2, 'a message without segments builds reasoning plus text');
  assertEqual(railLabel(blocks()[0]), 'Reasoning', 'legacy reasoning first');
  assertEqual(blockTextarea(blocks()[0]).value, 'thoughts', 'legacy reasoning is editable');
  assertEqual(blockTextarea(blocks()[1]).value, 'plain text', 'legacy content is editable');

  await openEditor({ content: '', segments: null, reasoning: null });
  assertEqual(blocks().length, 1, 'an empty message still gets one text block');
  assertEqual(railLabel(blocks()[0]), 'Text', 'the sole block is text');
}

// ── saving posts the edited blocks back as segments ──
async function savesEditedBlocks() {
  await openEditor({ content: 'x', segments: SEGMENTS });
  var tas = blocksContainer.querySelectorAll('[data-ui="edit-block-ta"]');
  assertEqual(tas.length, 3, 'only text and reasoning blocks carry an editor');
  tas[0].value = 'before edited';
  tas[1].value = 'think <new> & "quoted"';
  tas[2].value = 'after edited';

  window.currentEditAttachments = [{ id: 'att1' }];
  closedModals.length = 0;
  refreshed.length = 0;
  fetchCalls.length = 0;
  await window.saveMessageEdit();

  assertEqual(fetchCalls.length, 1, 'saving makes exactly one request');
  assertEqual(fetchCalls[0].url, '/api/chats/chat1/messages/msg1', 'it patches the edited message');
  assertEqual(fetchCalls[0].opts.method, 'PATCH', 'the request is a PATCH');
  var body = JSON.parse(fetchCalls[0].opts.body);
  assertEqual(body.content, 'before edited\nafter edited', 'text blocks are joined into content');
  assertEqual(body.reasoning, 'think <new> & "quoted"', 'the edited reasoning is saved as text');
  assertDeepEqual(body.segments, [
    { type: 'text', content: 'before edited' },
    { type: 'tool_boundary', tool_calls: SEGMENTS[1].tool_calls },
    { type: 'reasoning', html: 'think &lt;new&gt; &amp; &quot;quoted&quot;', index: 1 },
    { type: 'text', content: 'after edited' },
  ], 'edited blocks are saved back as segments in order');
  assertDeepEqual(body.attachment_ids, ['att1'], 'the kept attachments travel with the edit');

  assertEqual(closedModals.length, 1, 'the editor closes on save');
  assertEqual(closedModals[0].id, 'modal-edit-message', 'the edit modal is the one that closes');
  assertEqual(closedModals[0].opts.discard, true, 'closing after a save discards dirty state');
  assertDeepEqual(refreshed, [['chat1', 'msg1']], 'the edited message is re-rendered');
}

// ── clearing a block deletes that segment ──
async function clearingABlockDropsIt() {
  await openEditor({ content: 'x', segments: SEGMENTS });
  var tas = blocksContainer.querySelectorAll('[data-ui="edit-block-ta"]');
  tas[0].value = '';
  tas[1].value = '   ';
  tas[2].value = '';
  window.currentEditAttachments = [];
  fetchCalls.length = 0;
  await window.saveMessageEdit();

  var body = JSON.parse(fetchCalls[0].opts.body);
  assertEqual(body.content, '', 'clearing every text block empties the content');
  assertEqual(body.reasoning, null, 'clearing the reasoning block saves null');
  assertDeepEqual(body.segments, [{ type: 'tool_boundary', tool_calls: SEGMENTS[1].tool_calls }],
    'only the untouched tool boundary survives');
}

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

// ── renderEditModalAttachments clears the thumbs and shows the empty note ──
(function () {
  window.currentEditAttachments = [];
  window.renderEditModalAttachments();
  assertEqual(attachmentsContainer.children.length, 0, 'no thumbs when empty');
  assert(!attachmentsEmpty.classList.contains('hidden'), 'empty note is shown');
})();

// ── renderEditModalAttachments renders attachments ──
(function () {
  window.currentEditAttachments = [
    { id: 'att1', file_path: '/img/test.png', mime_type: 'image/png' },
  ];
  window.renderEditModalAttachments();
  assert(attachmentsContainer.children.length >= 1, 'attachments rendered');
  assert(attachmentsEmpty.classList.contains('hidden'), 'empty note is hidden with attachments');
  window.currentEditAttachments = [];
})();

// ── a thumb opens the lightbox, like the character editor's media grid ──
(function () {
  global._lightboxSrc = null;
  window.currentEditAttachments = [
    { id: 'att1', file_path: 'assets/attachments/x.png', mime_type: 'image/png' },
  ];
  window.renderEditModalAttachments();
  attachmentsContainer.children[0].children[0]._opts.onClick();
  assertEqual(global._lightboxSrc, '/assets/attachments/x.png', 'thumb click opens the lightbox');

  window.currentEditAttachments = [
    { id: 'att2', file_path: 'blob:preview', mime_type: 'image/png' },
  ];
  window.renderEditModalAttachments();
  attachmentsContainer.children[0].children[0]._opts.onClick();
  assertEqual(global._lightboxSrc, 'blob:preview', 'external src is not prefixed');
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
(async function () {
  var steps = [rendersBlocks, alwaysOffersTextBlock, savesEditedBlocks, clearingABlockDropsIt];
  for (var i = 0; i < steps.length; i++) {
    try {
      await steps[i]();
    } catch (e) {
      assert(false, steps[i].name + ' threw: ' + e.message);
    }
  }
  h.printSummary();
})();
