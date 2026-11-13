function openLightbox(src) {
  const img = document.getElementById('lightbox-img');
  img.setAttribute('src', src);
  window.ModalController.open('lightbox');
}

const Cropper = window.Cropper.default;
const CROP_MAX_EDGE = 2048;
const CROP_WORKER_URL = '/static/js/ui/crop-worker.js';

let cropper = null;
let currentCropCallback = null;
let currentCropOptions = null;
let currentCropUrl = null;
let currentCropFile = null;

function cropInWorker(file, rect, size, type, quality) {
  return new Promise((resolve, reject) => {
    let worker;
    try {
      worker = new Worker(CROP_WORKER_URL);
    } catch (error) {
      reject(error);
      return;
    }
    worker.onmessage = (event) => {
      worker.terminate();
      if (event.data.blob) resolve(event.data.blob);
      else reject(new Error(event.data.error || 'crop failed'));
    };
    worker.onerror = (event) => {
      worker.terminate();
      reject(new Error(event.message || 'crop failed'));
    };
    worker.postMessage({ file, ...rect, ...size, type, quality });
  });
}

function openCropModal(file, callback, options = {}) {
  const container = document.getElementById('crop-container');

  currentCropCallback = callback;
  currentCropOptions = options;

  if (currentCropUrl) URL.revokeObjectURL(currentCropUrl);
  const url = URL.createObjectURL(file);
  currentCropUrl = url;
  currentCropFile = file;

  window.ModalController.open('crop-modal');
  _cropSaveBtn.disabled = false;

  if (cropper) {
    cropper.destroy();
  }

  const aspectRatio = options.aspectRatio !== undefined ? options.aspectRatio : 1;
  const aspectAttr = aspectRatio > 0 ? ` aspect-ratio="${aspectRatio}"` : '';
  const template =
    '<cropper-canvas>' +
    '<cropper-image></cropper-image>' +
    '<cropper-shade hidden></cropper-shade>' +
    '<cropper-handle action="select" plain></cropper-handle>' +
    `<cropper-selection initial-coverage="0.8" movable resizable${aspectAttr}>` +
    '<cropper-grid role="grid" bordered covered></cropper-grid>' +
    '<cropper-crosshair centered></cropper-crosshair>' +
    '<cropper-handle action="move" theme-color="rgba(255, 255, 255, 0.35)"></cropper-handle>' +
    '<cropper-handle action="n-resize"></cropper-handle>' +
    '<cropper-handle action="e-resize"></cropper-handle>' +
    '<cropper-handle action="s-resize"></cropper-handle>' +
    '<cropper-handle action="w-resize"></cropper-handle>' +
    '<cropper-handle action="ne-resize"></cropper-handle>' +
    '<cropper-handle action="nw-resize"></cropper-handle>' +
    '<cropper-handle action="se-resize"></cropper-handle>' +
    '<cropper-handle action="sw-resize"></cropper-handle>' +
    '</cropper-selection>' +
    '</cropper-canvas>';

  const image = new Image();
  image.src = url;
  image.alt = 'Image to crop';

  cropper = new Cropper(image, { container, template });

  const canvas = cropper.getCropperCanvas();
  const cropperImage = cropper.getCropperImage();
  const selection = cropper.getCropperSelection();

  cropperImage.$ready(() => {
    const box = canvas.getBoundingClientRect();
    const fit = cropperImage.getBoundingClientRect();
    let x = fit.left - box.left;
    let y = fit.top - box.top;
    let width = fit.width;
    let height = fit.height;

    if (aspectAttr) {
      if (width / height > aspectRatio) {
        const fitted = height * aspectRatio;
        x += (width - fitted) / 2;
        width = fitted;
      } else {
        const fitted = width / aspectRatio;
        y += (height - fitted) / 2;
        height = fitted;
      }
    }

    const coverage = 0.9;
    x += (width * (1 - coverage)) / 2;
    y += (height * (1 - coverage)) / 2;
    width *= coverage;
    height *= coverage;

    selection.$change(x, y, width, height);
  });
}

function closeCropModal() {
  window.ModalController.close('crop-modal', { discard: true });
}

// Every close path (X, Cancel, ESC, backdrop) funnels through the controller,
// so teardown lives here instead of in each caller.
ModalController.onClose('lightbox', () => {
  document.getElementById('lightbox-img').removeAttribute('src');
});

ModalController.onClose('crop-modal', () => {
  if (cropper) {
    cropper.destroy();
    cropper = null;
  }
  if (currentCropUrl) {
    URL.revokeObjectURL(currentCropUrl);
    currentCropUrl = null;
  }
  currentCropFile = null;
  currentCropCallback = null;
  currentCropOptions = null;
});

const _cropSaveBtn = document.getElementById('crop-save-btn');
if (_cropSaveBtn) {
  _cropSaveBtn.addEventListener('click', () => {
    if (!cropper || !currentCropCallback) return;

    const cb = currentCropCallback;
    const file = currentCropFile;
    const selection = cropper.getCropperSelection();
    const image = cropper.getCropperImage();
    if (!file || !selection || !image) return;

    const [a, , , d, e, f] = image.$getTransform();
    // The matrix' translation is relative to the image centre, not the canvas
    // origin (cropper draws it as translate(centre) · matrix · translate(-centre)).
    const left = e + (image.offsetWidth / 2) * (1 - a);
    const top = f + (image.offsetHeight / 2) * (1 - d);
    const rect = {
      sx: (selection.x - left) / a,
      sy: (selection.y - top) / d,
      sw: selection.width / a,
      sh: selection.height / d,
    };
    const shrink = Math.min(1, CROP_MAX_EDGE / Math.max(rect.sw, rect.sh));
    const size = {
      width: Math.round(rect.sw * shrink),
      height: Math.round(rect.sh * shrink),
    };
    const fmt = (currentCropOptions && currentCropOptions.format) || 'webp';
    const quality = fmt === 'webp' ? 0.9 : undefined;
    const type = 'image/' + fmt;

    const drawer =
      typeof Worker === 'function' && typeof OffscreenCanvas === 'function'
        ? () => cropInWorker(file, rect, size, type, quality)
        : () =>
            selection.$toCanvas(size).then(
              (canvas) =>
                new Promise((resolve) => {
                  canvas.toBlob(resolve, type, quality);
                }),
            );

    _cropSaveBtn.disabled = true;

    requestAnimationFrame(() => {
      drawer()
        .then((blob) => {
          if (!blob) throw new Error('empty crop');
          cb(blob);
          closeCropModal();
        })
        .catch(() => {
          _cropSaveBtn.disabled = false;
          showErrorToast('Could not crop the image.');
        });
    });
  });
}
