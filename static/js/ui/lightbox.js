function openLightbox(src) {
  const img = document.getElementById('lightbox-img');
  img.setAttribute('src', src);
  window.ModalController.open('lightbox');
}

function closeLightbox() {
  window.ModalController.close('lightbox', { discard: true });
}

const Cropper = window.Cropper.default;

let cropper = null;
let currentCropCallback = null;
let currentCropOptions = null;

function openCropModal(file, callback, options = {}) {
  const container = document.getElementById('crop-container');

  currentCropCallback = callback;
  currentCropOptions = options;

  const url = URL.createObjectURL(file);

  window.ModalController.open('crop-modal');

  if (cropper) {
    cropper.destroy();
  }

  const aspectRatio = options.aspectRatio !== undefined ? options.aspectRatio : 1;

  const image = new Image();
  image.src = url;
  image.alt = 'Image to crop';

  setTimeout(() => {
    cropper = new Cropper(image, {
      container: container,
      template:
        '<cropper-canvas>' +
        '<cropper-image></cropper-image>' +
        '<cropper-shade hidden></cropper-shade>' +
        '<cropper-handle action="select" plain></cropper-handle>' +
        '<cropper-selection initial-coverage="0.8" movable resizable aspect-ratio="' +
        aspectRatio +
        '">' +
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
        '</cropper-canvas>',
    });
  }, 50);
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
  currentCropCallback = null;
  currentCropOptions = null;
});

const _cropSaveBtn = document.getElementById('crop-save-btn');
if (_cropSaveBtn) {
  _cropSaveBtn.addEventListener('click', () => {
    if (!cropper || !currentCropCallback) return;

    let getOpts = {};

    if (currentCropOptions && currentCropOptions.aspectRatio === 1) {
      getOpts.width = 2048;
      getOpts.height = 2048;
    }

    const cb = currentCropCallback;
    const selection = cropper.getCropperSelection();
    if (!selection) return;

    const fmt = (currentCropOptions && currentCropOptions.format) || 'webp';

    selection.$toCanvas(getOpts).then((canvas) => {
      canvas.toBlob((blob) => {
        cb(blob);
        closeCropModal();
      }, 'image/' + fmt, fmt === 'webp' ? 0.9 : undefined);
    });
  });
}

function handleAvatarUpload(fileInput, endpoint, successCallback) {
  if (!fileInput.files || !fileInput.files[0]) return;

  const file = fileInput.files[0];

  openCropModal(file, (croppedBlob) => {
    const formData = new FormData();
    formData.append('file', croppedBlob, 'avatar.webp');

    fetch(endpoint, {
      method: 'POST',
      body: formData,
    })
      .then((r) => r.json())
      .then((data) => {
        if (successCallback) {
          successCallback(data);
        } else {
          window.location.reload();
        }
      });
  });

  fileInput.value = '';
}
