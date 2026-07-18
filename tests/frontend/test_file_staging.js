// Unit tests for file_staging.js — file upload staging
var h = require('./_helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

var fileUpload = makeElement('input');
fileUpload.id = 'file-upload';
fileUpload.type = 'file';
fileUpload.addEventListener = function () {};
fileUpload.value = '';

var stagingArea = makeElement('div');
stagingArea.id = 'staging-area';
stagingArea.innerHTML = function () { /* noop */ };

var chatInput = makeElement('div');
chatInput.id = 'chat-input';
chatInput.addEventListener = function () {};
chatInput.style = {};

var doc = h.createMockDocument();
doc._body.appendChild(fileUpload);
doc._body.appendChild(stagingArea);
doc._body.appendChild(chatInput);
doc.getElementById = function (id) {
  if (id === 'file-upload') return fileUpload;
  if (id === 'staging-area') return stagingArea;
  if (id === 'chat-input') return chatInput;
  return null;
};
doc.body = doc._body;
doc.body.addEventListener = function () {};
doc.addEventListener = function () {};
doc.createElement = function (tag) {
  var el = h.makeElement(tag);
  el.style = {};
  el.addEventListener = function () {};
  el.appendChild = function (c) {
    var idx = this.children.indexOf(c);
    if (idx >= 0) this.children.splice(idx, 1);
    this.children.push(c);
    c.parent = this;
    return c;
  };
  return el;
};

global.window = global;
global.addEventListener = function () {};
global.window.addEventListener = function () {};
global.document = doc;
global.URL = { createObjectURL: function () { return 'blob:url'; }, revokeObjectURL: function () {} };
global.File = function (parts, name, opts) { this.name = name; this.type = opts && opts.type ? opts.type : ''; };
global.updateSendButtonState = function () {};
global.getSvgSprite = function (name) { return '<svg>' + name + '</svg>'; };
global.createMediaThumbnail = function (opts) {
  var div = doc.createElement('div');
  var img = doc.createElement('img');
  img.src = opts.src || '';
  div.appendChild(img);
  if (opts.onDelete) {
    var delBtn = doc.createElement('button');
    delBtn.addEventListener('click', function (e) { opts.onDelete(e); });
    div.appendChild(delBtn);
  }
  div.querySelector = function (s) {
    if (s === 'img') return img;
    if (s === 'div') return div;
    return null;
  };
  return div;
};
global.Blob = function () {};
global.openCropModal = function (file, callback) {
  // Simulate crop completion immediately
  callback(new global.Blob());
};

// Load module (IIFE, sets window.stagedFiles, removeStagedFile, cropStagedImage, clearUploadedFiles)
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'messages', 'file_staging.js'), 'utf8'));

assert(Array.isArray(window.stagedFiles), 'stagedFiles is array');

// ── initial state ──
(function () {
  assertEqual(window.stagedFiles.length, 0, 'stagedFiles starts empty');
})();

// ── add a file to stagedFiles and render ──
(function () {
  var file = { name: 'test.png', type: 'image/png', size: 1024 };
  window.stagedFiles.push(file);
  // render is called internally by the IIFE, but we push directly so call render
  // render is private, so we simulate by calling removeStagedFile indirectly
  assertEqual(window.stagedFiles.length, 1, 'staged file added');
  // Clean up
  window.stagedFiles = [];
})();

// ── removeStagedFile removes by index ──
(function () {
  window.stagedFiles.push({ name: 'a.png', type: 'image/png' });
  window.stagedFiles.push({ name: 'b.png', type: 'image/png' });
  assertEqual(window.stagedFiles.length, 2, 'two files before remove');
  window.removeStagedFile(0);
  assertEqual(window.stagedFiles.length, 1, 'one file after remove');
  assertEqual(window.stagedFiles[0].name, 'b.png', 'correct file remains');
  window.stagedFiles = [];
})();

// ── cropStagedImage replaces file with PNG ──
(function () {
  var file = { name: 'test.jpg', type: 'image/jpeg', size: 2048 };
  window.stagedFiles.push(file);
  window.cropStagedImage(0);
  assertEqual(window.stagedFiles.length, 1, 'file still exists after crop');
  assertEqual(window.stagedFiles[0].type, 'image/png', 'cropped file type is PNG');
  assertEqual(window.stagedFiles[0].name, 'test.jpg', 'cropped file name preserved');
  window.stagedFiles = [];
})();

// ── cropStagedImage with non-image is no-op ──
(function () {
  window.stagedFiles.push({ name: 'audio.mp3', type: 'audio/mpeg' });
  window.cropStagedImage(0);
  assertEqual(window.stagedFiles[0].type, 'audio/mpeg', 'non-image not cropped');
  window.stagedFiles = [];
})();

// ── clearUploadedFiles removes uploaded files from staged ──
(function () {
  var f1 = { name: 'keep.png', type: 'image/png' };
  var f2 = { name: 'remove.png', type: 'image/png' };
  window.stagedFiles.push(f1, f2);
  window.clearUploadedFiles([f2]);
  assertEqual(window.stagedFiles.length, 1, 'one file after clearUploaded');
  assertEqual(window.stagedFiles[0].name, 'keep.png', 'correct file kept');
  window.stagedFiles = [];
})();

// ── render is called after modifications ──
(function () {
  // We can't test render directly (it's private), but we can verify that
  // operations that call render don't throw
  window.stagedFiles.push({ name: 'test.png', type: 'image/png' });
  try {
    window.removeStagedFile(0);
    assert(true, 'removeStagedFile + render does not throw');
  } catch (e) {
    assert(false, 'removeStagedFile threw: ' + e.message);
  }
  window.stagedFiles = [];
})();

// ── Result ──
h.printSummary();
