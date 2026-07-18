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

let cropper = null;
let currentCropCallback = null;
let currentCropOptions = null;

function openCropModal(file, callback, options = {}) {
  const modal = document.getElementById('crop-modal');
  const img = document.getElementById('crop-image');

  currentCropCallback = callback;
  currentCropOptions = options;

  const url = URL.createObjectURL(file);
  img.src = url;

  modal.classList.remove('hidden');
  modal.classList.add('flex');

  if (cropper) {
    cropper.destroy();
  }

  setTimeout(() => {
    cropper = new Cropper(img, {
      aspectRatio: options.aspectRatio !== undefined ? options.aspectRatio : 1,
      viewMode: 1,
      dragMode: 'move',
      background: false,
      autoCropArea: 0.8,
      guides: true,
      center: true,
      highlight: false,
      cropBoxMovable: true,
      cropBoxResizable: true,
      toggleDragModeOnDblclick: false,
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
  document.getElementById('crop-image').src = '';
  currentCropCallback = null;
  currentCropOptions = null;
}

const _cropSaveBtn = document.getElementById('crop-save-btn');
if (_cropSaveBtn) {
  _cropSaveBtn.addEventListener('click', () => {
    if (!cropper || !currentCropCallback) return;

    let getOpts = {
      imageSmoothingEnabled: true,
      imageSmoothingQuality: 'high',
    };

    if (currentCropOptions && currentCropOptions.aspectRatio === 1) {
      getOpts.width = 512;
      getOpts.height = 512;
    }

    const cb = currentCropCallback;
    cropper.getCroppedCanvas(getOpts).toBlob((blob) => {
      cb(blob);
      closeCropModal();
    }, 'image/png');
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
