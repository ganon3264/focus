// Unit tests for char-blocks.js — custom character block list glue: load,
// create, inline patch, enable toggle, delete, media, reorder.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;

var path = require('path');
var fs = require('fs');
var realSetTimeout = global.setTimeout;

var env = h.setupBrowserGlobals(global);
var doc = env.document;

function createHxMock(response) {
  var calls = [];
  var fn = function (url, opts) {
    calls.push({ url: url, opts: opts });
    return Promise.resolve(typeof response === 'function' ? response(url, opts) : (response || { ok: true }));
  };
  fn._calls = calls;
  fn._last = function () { return calls[calls.length - 1] || null; };
  fn._reset = function () { calls.length = 0; };
  return fn;
}

var hxFetch = createHxMock({
  ok: true,
  json: function () { return Promise.resolve({ id: 'new-block' }); },
});
var hxGet = createHxMock();
global.hxFetch = hxFetch;
global.hxGet = hxGet;
global.jsonOpts = h.jsonOpts;
global.hxJson = function (url, method, body) {
  return hxFetch(url, h.jsonOpts(method, body));
};

global.Sortable = function (el, opts) {
  this.el = el;
  this.options = opts;
  this.destroy = function () { el._sortable = null; };
  el._sortable = this;
};

var expanded = {};
global.expandGet = function (set, key) { return !!expanded[set + ':' + key]; };
global.expandToggle = function (set, key) {
  var k = set + ':' + key;
  expanded[k] = !expanded[k];
  return expanded[k];
};

var toasts = [];
global.showErrorToast = function (m) { toasts.push(m); };

var opened = [];
global.openModal = function (id) { opened.push(id); };

var onOpen = {};
global.ModalController = {
  onOpen: function (id, fn) { onOpen[id] = fn; },
};

var confirmed = [];
global.customConfirm = function (msg, cb) { confirmed.push(msg); cb(); };

var swapHandlers = {};
doc.addEventListener = function (type, fn) { swapHandlers[type] = fn; };

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'api-paths.js'), 'utf8'));
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'char-blocks.js'), 'utf8'));

function el(tag, attrs) {
  var node = h.makeElement(tag || 'div');
  Object.keys(attrs || {}).forEach(function (k) {
    if (k === 'id') node.id = attrs[k];
    else if (k === 'class') attrs[k].split(' ').forEach(function (c) { node.classList.add(c); });
    else node.setAttribute(k, attrs[k]);
  });
  return node;
}

var modalEl = el('div', { id: 'modal-char-blocks' });
modalEl.dataset.charId = 'ch1';
doc.body.appendChild(modalEl);

var charIdInput = el('input', { id: 'edit-char-id' });
charIdInput.value = 'ch1';
doc.body.appendChild(charIdInput);

var container = el('div', { id: 'char-blocks-container' });
var list = el('div', { 'data-ui': 'char-blocks-sortable' });
container.appendChild(list);
doc.body.appendChild(container);

function addBlockRow(id) {
  var item = el('div', { 'data-ui': 'char-block', 'data-block-id': id });
  var header = el('div', { 'data-ui': 'char-block-title' });
  var name = el('input', { 'data-ui': 'char-block-name' });
  name.value = 'Block ' + id;
  var role = el('input', { name: 'role' });
  role.value = 'system';
  var content = el('textarea', { 'data-ui': 'char-block-content' });
  content.value = 'body ' + id;
  var toggle = el('div', { 'data-ui': 'char-block-enabled', class: 'switch active' });
  var del = el('button', { 'data-action': 'actionDeleteCharBlock' });
  var delMedia = el('button', { 'data-action': 'actionDeleteCharBlockMedia' });
  var thumb = el('div', { 'data-image-id': 'img-' + id });
  thumb.appendChild(delMedia);
  item.appendChild(header);
  item.appendChild(name);
  item.appendChild(role);
  item.appendChild(content);
  item.appendChild(toggle);
  item.appendChild(del);
  item.appendChild(thumb);
  list.appendChild(item);
  return { item: item, name: name, role: role, content: content, toggle: toggle, del: del, delMedia: delMedia };
}

function tick() {
  return new Promise(function (resolve) { realSetTimeout(resolve, 0); });
}

// The list is wired from htmx's afterSwap, not the hxGet promise.
function runAfterSwap() {
  swapHandlers['htmx:afterSwap']({ detail: { target: container } });
}

async function main() {
  assertEqual(onOpen['modal-char-blocks'] !== undefined, true, 'blocks modal registers an onOpen loader');

  // ── load ──
  hxGet._reset();
  window.reloadCharBlocks();
  await tick();
  assertEqual(hxGet._last().url, '/partials/char-blocks/ch1', 'load hits the list partial');
  assertDeepEqual(hxGet._last().opts, { target: '#char-blocks-container', swap: 'innerHTML' }, 'load swaps the container');

  // ── create ──
  hxFetch._reset();
  hxGet._reset();
  window.actionAddCharBlock();
  await tick();
  await tick();
  var create = hxFetch._calls[0];
  assertEqual(create.url, '/api/characters/ch1/blocks', 'create posts to the blocks collection');
  assertDeepEqual(
    JSON.parse(create.opts.body),
    { name: 'New Block', content: '', role: 'system' },
    'create sends the seed block',
  );
  assertEqual(expanded['charBlocks:new-block'], true, 'a created block arrives expanded');
  assertEqual(hxGet._last().url, '/partials/char-blocks/ch1', 'create reloads the list');

  // ── inline field patches ──
  var a = addBlockRow('b1');
  runAfterSwap();
  hxFetch._reset();
  window.actionRenameCharBlock(a.name);
  await tick();
  assertEqual(hxFetch._last().url, '/api/characters/ch1/blocks/b1', 'rename PATCHes the block');
  assertDeepEqual(JSON.parse(hxFetch._last().opts.body), { name: 'Block b1' }, 'rename sends only the name');

  hxFetch._reset();
  window.actionSetCharBlockContent(a.content);
  await tick();
  assertDeepEqual(JSON.parse(hxFetch._last().opts.body), { content: 'body b1' }, 'content edit sends only the content');

  // ── role change re-renders the row (the role is its left edge) ──
  hxFetch._reset();
  hxGet._reset();
  a.role.value = 'assistant';
  window.actionSetCharBlockRole(a.role);
  await tick();
  await tick();
  assertDeepEqual(JSON.parse(hxFetch._last().opts.body), { role: 'assistant' }, 'role PATCH sends the role');
  assertEqual(hxGet._last().url, '/partials/char-block/ch1/b1', 'role change re-renders the row');

  // ── enable toggle ──
  hxFetch._reset();
  window.actionToggleCharBlock(a.toggle);
  await tick();
  assertEqual(a.toggle.classList.contains('active'), false, 'toggle flips off immediately');
  assertEqual(a.item.classList.contains('disabled'), true, 'disabled row is dimmed');
  assertDeepEqual(JSON.parse(hxFetch._last().opts.body), { enabled: false }, 'toggle PATCHes enabled=false');

  // ── delete confirms first ──
  hxFetch._reset();
  hxGet._reset();
  confirmed.length = 0;
  a.del.closest = function () { return a.item; };
  window.actionDeleteCharBlock(a.del);
  await tick();
  await tick();
  assertEqual(confirmed.length, 1, 'delete asks for confirmation');
  assertEqual(hxFetch._last().opts.method, 'DELETE', 'delete issues a DELETE');
  assertEqual(hxFetch._last().url, '/api/characters/ch1/blocks/b1', 'delete hits the block url');

  // ── media delete ──
  hxFetch._reset();
  hxGet._reset();
  a.delMedia.closest = function (sel) {
    return sel === '[data-ui="char-block"]' ? a.item : el('div', { 'data-image-id': 'img-b1' });
  };
  window.actionDeleteCharBlockMedia(a.delMedia);
  await tick();
  await tick();
  assertEqual(hxFetch._last().opts.method, 'DELETE', 'media delete issues a DELETE');
  assertEqual(hxFetch._last().url, '/api/characters/ch1/blocks/b1/images/img-b1', 'media delete hits the image url');

  // ── reorder ──
  addBlockRow('b2');
  addBlockRow('b3');
  runAfterSwap();
  assert(list._sortable !== null, 'afterSwap wires the sortable');
  assertEqual(list._sortable.options.handle, '.char-block-handle', 'the grip is the drag handle');
  list.appendChild(list.children[0]); // move the first block to the end
  hxFetch._reset();
  list._sortable.options.onEnd();
  await tick();
  var reorder = hxFetch._last();
  assertEqual(reorder.url, '/api/characters/ch1/blocks/reorder', 'reorder posts to the reorder route');
  assertDeepEqual(
    JSON.parse(reorder.opts.body),
    { ids: ['b2', 'b3', 'b1'] },
    'reorder sends the DOM order',
  );

  // ── a failed save toasts, and the toggle reverts ──
  toasts.length = 0;
  hxFetch = createHxMock({ ok: false });
  global.hxFetch = hxFetch;
  var b = addBlockRow('b4');
  window.actionToggleCharBlock(b.toggle);
  await tick();
  assertEqual(toasts.length, 1, 'failed toggle raises a toast');
  assertEqual(b.toggle.classList.contains('active'), true, 'failed toggle reverts the switch');
  assertEqual(b.item.classList.contains('disabled'), false, 'failed toggle un-dims the row');

  // ── opening the modal from the editor ──
  opened.length = 0;
  modalEl.dataset.charId = '';
  window.actionOpenCharBlocks();
  assertEqual(modalEl.dataset.charId, 'ch1', 'the editor hands its character id to the modal');
  assertEqual(opened[0], 'modal-char-blocks', 'the blocks modal opens');

  h.printSummary();
}

main();
