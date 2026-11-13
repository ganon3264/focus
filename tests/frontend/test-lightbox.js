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
global.URL = {
  createObjectURL: function () { return 'blob:url'; },
  revokeObjectURL: function () {},
};
global.Image = function () { this.src = ''; this.alt = ''; };
global.Blob = function () {};
global.setTimeout = function (fn) { fn(); };
global.requestAnimationFrame = function (fn) { fn(); };
global.showErrorToast = function () {};

// A promise-like that runs its callbacks synchronously, so the tests stay flat.
function syncChain(value) {
  return {
    then: function (cb) { return syncChain(cb(value)); },
    catch: function () { return syncChain(value); },
  };
}

// Cropper.js v2 mock with default export
var cropperInstance = null;
var cropperCanvas = { getBoundingClientRect: function () { return { left: 0, top: 0, width: 600, height: 400 }; } };
var cropperImage = {
  offsetWidth: 2400,
  offsetHeight: 960,
  getBoundingClientRect: function () { return { left: 0, top: 80, width: 600, height: 240 }; },
  // 2400px source rendered 600px wide, its top 80px down the 400px canvas
  $getTransform: function () { return [0.25, 0, 0, 0.25, 0, -280]; },
  $ready: function (cb) { cb(); },
};
var lastChange = null;
var lastCanvasOpts = null;
var cropperSelection = {
  x: 0,
  y: 0,
  width: 0,
  height: 0,
  $toCanvas: function (opts) {
    lastCanvasOpts = opts;
    var canvas = { toBlob: function (cb) { cb(new Blob()); } };
    return syncChain(canvas);
  },
  $change: function (x, y, width, height) {
    lastChange = { x: x, y: y, width: width, height: height };
    this.x = x;
    this.y = y;
    this.width = width;
    this.height = height;
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
  getCropperCanvas: function () { return cropperCanvas; },
  getCropperImage: function () { return cropperImage; },
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

// ── the crop is taken at the source resolution, not the on-screen one ──
(function () {
  lastCanvasOpts = null;
  window.openCropModal(new Blob(), function () {}, { aspectRatio: 1 });
  cropSaveBtn.click();
  assertEqual(lastCanvasOpts.width, 864, 'crop canvas is 4x the 216px selection (2400px source rendered in 600px)');
  assertEqual(lastCanvasOpts.height, 864, 'crop canvas keeps the selection aspect');
})();

// ── a crop larger than the pipeline's 2048 ceiling is scaled down, not drawn huge ──
(function () {
  lastCanvasOpts = null;
  cropperSelection.$change(0, 80, 600, 400);
  window.openCropModal(new Blob(), function () {}, { aspectRatio: NaN });
  cropperSelection.$change(0, 80, 600, 400);
  cropSaveBtn.click();
  assertEqual(lastCanvasOpts.width, 2048, 'oversized crop is capped at 2048 on its long edge');
  assertEqual(lastCanvasOpts.height, 1365, 'capped crop keeps its aspect');
})();

// ── the initial selection sits inside the image, not the whole canvas ──
(function () {
  lastChange = null;
  window.openCropModal(new Blob(), function () {}, { aspectRatio: 1 });
  assertEqual(lastChange.width, 216, 'square selection is 90% of the image height');
  assertEqual(lastChange.height, 216, 'square selection stays square');
  assertEqual(lastChange.x, 192, 'square selection is centred on the image');
  assertEqual(lastChange.y, 92, 'square selection is inset inside the image');
  window.closeCropModal();
})();

(function () {
  lastChange = null;
  window.openCropModal(new Blob(), function () {}, { aspectRatio: NaN });
  assertEqual(lastChange.width, 540, 'free selection spans 90% of a wide image');
  assertEqual(lastChange.height, 216, 'free selection spans 90% of the image height');
  assertEqual(Math.round(lastChange.x), 30, 'free selection is centred horizontally');
  window.closeCropModal();
})();

// ── Result ──
h.printSummary();
