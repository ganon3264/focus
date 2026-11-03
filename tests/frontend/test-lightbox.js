// Unit tests for lightbox.js — image lightbox + crop modal
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

// Build DOM
var lightboxEl = makeElement('div');
lightboxEl.id = 'lightbox';
lightboxEl.dataset.ui = 'modal-overlay';
lightboxEl.classList.add('modal-overlay');
lightboxEl.classList.add('hidden');
var lightboxImg = makeElement('img');
lightboxImg.id = 'lightbox-img';
lightboxEl.appendChild(lightboxImg);

var cropModal = makeElement('div');
cropModal.id = 'crop-modal';
cropModal.dataset.ui = 'modal-overlay';
cropModal.classList.add('modal-overlay');
cropModal.classList.add('hidden');
var cropContainer = makeElement('div');
cropContainer.id = 'crop-container';
var cropSaveBtn = makeElement('button');
cropSaveBtn.id = 'crop-save-btn';
// Add event listener support
cropSaveBtn.addEventListener = function (event, handler) {
  if (event === 'click') this._clickHandler = handler;
};
cropSaveBtn.click = function () { if (this._clickHandler) this._clickHandler(); };
cropModal.addEventListener = function (type, fn) {
  this._handlers = this._handlers || {};
  (this._handlers[type] = this._handlers[type] || []).push(fn);
};
cropModal.dispatchEvent = function (ev) {
  var hs = this._handlers && this._handlers[ev.type];
  if (hs) hs.forEach(function (fn) { fn(ev); });
  return true;
};
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
doc._handlers = {};
doc.addEventListener = function (type, fn) {
  (this._handlers[type] = this._handlers[type] || []).push(fn);
};

var CustomEventCtor = h.createMockCustomEvent();

global.window = global;
global.document = doc;
global.CustomEvent = CustomEventCtor;
global.dispatchEvent = function () {};
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

// Load the controller first — lightbox.js drives every overlay through it
var MODAL_JS = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'modal.js'), 'utf8');
eval(MODAL_JS);

// Load module — append export assignment since bare function declarations aren't hoisted to global
var src = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'lightbox.js'), 'utf8');
eval(src + '\nwindow.openLightbox=openLightbox;window.openCropModal=openCropModal;window.closeCropModal=closeCropModal;');

// ── openLightbox shows overlay and sets src ──
(function () {
  lightboxEl.classList.add('hidden');
  window.openLightbox('/path/to/img.jpg');
  assert(!lightboxEl.classList.contains('hidden'), 'lightbox visible after openLightbox');
  assertEqual(window.ModalController.isOpen('lightbox'), true, 'openLightbox pushes lightbox on the stack');
  assertEqual(lightboxImg.getAttribute('src'), '/path/to/img.jpg', 'lightbox img src set');
})();

// ── openCropModal creates Cropper instance ──
(function () {
  var file = new Blob();
  var callbackCalled = false;
  window.openCropModal(file, function () { callbackCalled = true; }, { aspectRatio: 1 });
  assert(!!cropperInstance, 'Cropper instance created');
  assert(!cropModal.classList.contains('hidden'), 'crop modal visible');
  assertEqual(window.ModalController.isOpen('crop-modal'), true, 'openCropModal pushes crop modal on the stack');
})();

// ── closeCropModal destroys cropper and hides modal ──
(function () {
  window.closeCropModal();
  assert(cropModal.classList.contains('hidden'), 'crop modal hidden after close');
  assertEqual(window.ModalController.isOpen('crop-modal'), false, 'closeCropModal pops the stack');
  assert(!cropperInstance, 'cropper set to null after close');
})();

// ── the shell close button (controller path) tears the cropper down ──
(function () {
  window.openCropModal(new Blob(), function () {}, { aspectRatio: 1 });
  assert(!!cropperInstance, 'cropper alive before shell close');

  window.closeModal('crop-modal');
  cropModal.dispatchEvent({ type: 'click', target: { closest: function () { return cropModal; } } });
  assert(!cropperInstance, 'cropper destroyed on controller close');
})();

// ── crop-save-btn handler exists and invokes callback ──
(function () {
  var callbackInvoked = false;
  window.openCropModal(new Blob(), function () { callbackInvoked = true; }, { aspectRatio: 1 });
  assert(!!cropperInstance, 'cropper instance for save test');
  cropSaveBtn.click();
  assert(callbackInvoked, 'crop save callback invoked via button');
})();

// ── Result ──
h.printSummary();
