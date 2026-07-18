function openLightbox(src) {
  const lb = document.getElementById('lightbox');
  const img = document.getElementById('lightbox-img');
  img.src = src;
  lb.classList.remove('hidden');
  lb.classList.add('flex');
}

function closeLightbox(e) {
  const lb = document.getElementById('lightbox');
  lb.classList.remove('flex');
  lb.classList.add('hidden');
  document.getElementById('lightbox-img').src = '';
}

const Cropper = window.Cropper.default;

let cropper = null;
let currentCropCallback = null;
let currentCropOptions = null;

function openCropModal(file, callback, options = {}) {
  const modal = document.getElementById('crop-modal');
  const container = document.getElementById('crop-container');

  currentCropCallback = callback;
  currentCropOptions = options;

  const url = URL.createObjectURL(file);

  modal.classList.remove('hidden');
  modal.classList.add('flex');

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
          '<cropper-selection initial-coverage="0.8" movable resizable aspect-ratio="' + aspectRatio + '">' +
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
        '</cropper-canvas>'
    });
  }, 50);
}

function closeCropModal() {
  const modal = document.getElementById('crop-modal');
  modal.classList.remove('flex');
  modal.classList.add('hidden');
  if (cropper) {
    cropper.destroy();
    cropper = null;
  }
  currentCropCallback = null;
  currentCropOptions = null;
}

const _cropSaveBtn = document.getElementById('crop-save-btn');
if (_cropSaveBtn) {
  _cropSaveBtn.addEventListener('click', () => {
    if (!cropper || !currentCropCallback) return;

    let getOpts = {};

    if (currentCropOptions && currentCropOptions.aspectRatio === 1) {
      getOpts.width = 512;
      getOpts.height = 512;
    }

    const cb = currentCropCallback;
    const selection = cropper.getCropperSelection();
    if (!selection) return;

    selection.$toCanvas(getOpts).then(canvas => {
      canvas.toBlob((blob) => {
        cb(blob);
        closeCropModal();
      }, 'image/png');
    });
  });
}

function handleAvatarUpload(fileInput, endpoint, successCallback) {
  if (!fileInput.files || !fileInput.files[0]) return;

  const file = fileInput.files[0];

  openCropModal(file, (croppedBlob) => {
    const formData = new FormData();
    formData.append('file', croppedBlob, 'avatar.png');

    fetch(endpoint, {
      method: 'POST',
      body: formData
    }).then(r => r.json()).then(data => {
      if (successCallback) {
        successCallback(data);
      } else {
        window.location.reload();
      }
    });
  });

  fileInput.value = '';
}
