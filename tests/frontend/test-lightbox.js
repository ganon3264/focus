// Unit tests for lightbox.js — image lightbox + crop modal
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

// Build DOM
var lightboxEl = makeElement('div');
lightboxEl.id = 'lightbox';
var lightboxImg = makeElement('img');
lightboxImg.id = 'lightbox-img';
lightboxEl.appendChild(lightboxImg);

var cropModal = makeElement('div');
cropModal.id = 'crop-modal';
var cropContainer = makeElement('div');
cropContainer.id = 'crop-container';
var cropSaveBtn = makeElement('button');
cropSaveBtn.id = 'crop-save-btn';
// Add event listener support
cropSaveBtn.addEventListener = function (event, handler) {
  if (event === 'click') this._clickHandler = handler;
};
cropSaveBtn.click = function () { if (this._clickHandler) this._clickHandler(); };
cropModal.appendChild(cropContainer);
cropModal.appendChild(cropSaveBtn);

var doc = h.createMockDocument();
doc._body.appendChild(lightboxEl);
doc._body.appendChild(cropModal);
doc.getElementById = function (id) {
  if (id === 'lightbox') return lightboxEl;
  if (id === 'lightbox-img') return lightboxImg;
  if (id === 'crop-modal') return cropModal;
  if (id === 'crop-container') return cropContainer;
  if (id === 'crop-save-btn') return cropSaveBtn;
  return null;
};
doc.body = doc._body;
doc.body.addEventListener = function () {};

global.window = global;
global.document = doc;
global.fetch = function () { return Promise.resolve({ ok: true }); };
global.URL = { createObjectURL: function () { return 'blob:url'; } };
global.Image = function () { this.src = ''; this.alt = ''; };
global.Blob = function () {};
global.setTimeout = function (fn) { fn(); };

// Cropper.js v2 mock with default export
var cropperInstance = null;
var $toCanvasCallback;
var cropperSelection = {
  $toCanvas: function (opts) {
    var canvas = { toBlob: function (cb) { cb(new Blob()); } };
    // Run .then(cb) synchronously via a custom thenable
    return { then: function (cb) { cb(canvas); } };
  },
};
function MockCropper(image, opts) {
  this._image = image;
  this._opts = opts;
  this.destroyed = false;
  cropperInstance = this;
  if (opts && opts.ready) { var self = this; setTimeout(function () { opts.ready.call(self); }, 0); }
}
MockCropper.prototype = {
  destroy: function () { this.destroyed = true; cropperInstance = null; },
  getCropperSelection: function () { return cropperSelection; },
};
MockCropper.default = MockCropper;
global.Cropper = MockCropper;

// Load module — append export assignment since bare function declarations aren't hoisted to global
var src = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'lightbox.js'), 'utf8');
eval(src + '\nwindow.openLightbox=openLightbox;window.closeLightbox=closeLightbox;window.openCropModal=openCropModal;window.closeCropModal=closeCropModal;window.handleAvatarUpload=handleAvatarUpload;');

// ── openLightbox shows overlay and sets src ──
(function () {
  lightboxEl.classList.add('hidden');
  window.openLightbox('/path/to/img.jpg');
  assert(!lightboxEl.classList.contains('hidden'), 'lightbox visible after openLightbox');
  assertEqual(lightboxImg.src, '/path/to/img.jpg', 'lightbox img src set');
})();

// ── closeLightbox hides overlay ──
(function () {
  window.closeLightbox();
  assert(lightboxEl.classList.contains('hidden'), 'lightbox hidden after close');
  assertEqual(lightboxImg.src, '', 'lightbox img src cleared');
})();

// ── openCropModal creates Cropper instance ──
(function () {
  var file = new Blob();
  var callbackCalled = false;
  window.openCropModal(file, function () { callbackCalled = true; }, { aspectRatio: 1 });
  assert(!!cropperInstance, 'Cropper instance created');
  assert(!cropModal.classList.contains('hidden'), 'crop modal visible');
})();

// ── closeCropModal destroys cropper and hides modal ──
(function () {
  cropModal.classList.remove('hidden');
  window.closeCropModal();
  assert(cropModal.classList.contains('hidden'), 'crop modal hidden after close');
  assert(!cropperInstance, 'cropper set to null after close');
})();

// ── crop-save-btn handler exists and invokes callback ──
(function () {
  var callbackInvoked = false;
  window.openCropModal(new Blob(), function () { callbackInvoked = true; }, { aspectRatio: 1 });
  assert(!!cropperInstance, 'cropper instance for save test');
  cropSaveBtn.click();
  assert(callbackInvoked, 'crop save callback invoked via button');
})();

// ── handleAvatarUpload + crop save triggers fetch ──
(function () {
  var uploadCalled = false;
  var oldFetch = global.fetch;
  global.fetch = function () { uploadCalled = true; return Promise.resolve({ json: function () { return {}; } }); };

  var fileInput = { files: [new Blob()], value: 'dummy' };
  window.handleAvatarUpload(fileInput, '/api/test/avatar', function () {});
  // User clicks save — triggers the crop callback which calls fetch
  cropSaveBtn.click();
  assert(uploadCalled, 'fetch called when crop completes');
  global.fetch = oldFetch;
})();

// ── handleAvatarUpload with empty input is no-op ──
(function () {
  var called = false;
  var oldFetch = global.fetch;
  global.fetch = function () { called = true; return Promise.resolve({ json: function () { return {}; } }); };

  window.handleAvatarUpload({ files: [] }, '/api/test/avatar', function () {});
  assert(!called, 'no fetch when files empty');

  window.handleAvatarUpload({}, '/api/test/avatar', function () {});
  assert(!called, 'no fetch when files missing');

  global.fetch = oldFetch;
})();

// ── Result ──
h.printSummary();
