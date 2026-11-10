(function () {
  window.stagedFiles = [];

  const fileUpload = document.getElementById('file-upload');
  const stagingArea = document.getElementById('staging-area');
  const input = document.getElementById('chat-input');

  function render() {
    if (!stagingArea) return;
    stagingArea.innerHTML = '';
    window.stagedFiles.forEach((f, idx) => {
      const el = document.createElement('div');
      el.className = 'staging-item';

      const isImage = f.type.startsWith('image/');
      const url = isImage ? URL.createObjectURL(f) : '';

      const thumbnail = window.createMediaThumbnail({
        src: isImage ? url : '',
        mimeType: f.type,
        size: 24,
        iconSize: 16,
        name: f.name,
        showName: false,
      });
      if (isImage) {
        const img = thumbnail.querySelector('img');
        img.addEventListener('load', function () { URL.revokeObjectURL(url); }, { once: true });

        const cropBtn = document.createElement('button');
        cropBtn.type = 'button';
        cropBtn.className = 'key sm scrim media-thumb-crop';
        cropBtn.title = 'Crop';
        cropBtn.setAttribute('aria-label', 'Crop attachment');
        cropBtn.innerHTML = window.getSvgSprite('crop', 12);
        cropBtn.addEventListener('click', function (e) {
          e.stopPropagation();
          window.cropStagedImage(idx);
        });
        thumbnail.appendChild(cropBtn);
      }
      el.appendChild(thumbnail);

      const nameSpan = document.createElement('span');
      nameSpan.className = 'staging-name';
      nameSpan.title = f.name;
      nameSpan.textContent = f.name;
      el.appendChild(nameSpan);

      const removeBtn = document.createElement('button');
      removeBtn.type = 'button';
      removeBtn.className = 'key sm danger';
      removeBtn.title = 'Remove';
      removeBtn.setAttribute('aria-label', 'Remove attachment');
      removeBtn.innerHTML = window.getSvgSprite('close', 14);
      removeBtn.addEventListener('click', function () {
        window.removeStagedFile(idx);
      });
      el.appendChild(removeBtn);

      stagingArea.appendChild(el);
    });

    var attachBtn = document.getElementById('attach-btn');
    if (attachBtn) {
      attachBtn.classList.toggle('has-files', window.stagedFiles.length > 0);
    }

    if (typeof updateSendButtonState === 'function') {
      updateSendButtonState();
    }
  }

  window.removeStagedFile = function (idx) {
    window.stagedFiles.splice(idx, 1);
    render();
  };

  window.cropStagedImage = function (idx) {
    const file = window.stagedFiles[idx];
    if (!file || !file.type.startsWith('image/')) return;
    if (typeof openCropModal !== 'function') return;

    openCropModal(
      file,
      (croppedBlob) => {
        const newFile = new File([croppedBlob], file.name, { type: 'image/png' });
        window.stagedFiles[idx] = newFile;
        render();
      },
      { aspectRatio: NaN, format: 'png' },
    );
  };

  window.clearUploadedFiles = function (uploadedFiles) {
    window.stagedFiles = window.stagedFiles.filter((f) => !uploadedFiles.includes(f));
    render();
  };

  if (fileUpload) {
    fileUpload.addEventListener('change', function (e) {
      if (e.target.files.length) {
        window.stagedFiles.push(...Array.from(e.target.files));
        render();
        e.target.value = '';
      }
    });
  }

  window.addEventListener('paste', (e) => {
    if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length > 0) {
      const newFiles = Array.from(e.clipboardData.files).filter((f) => f.type.startsWith('image/'));
      if (newFiles.length > 0) {
        window.stagedFiles.push(...newFiles);
        render();
        e.preventDefault();
      }
    }
  });

  if (input) {
    input.addEventListener('dragover', (e) => {
      e.preventDefault();
      input.style.background = 'var(--surface-3)';
    });
    input.addEventListener('dragleave', (e) => {
      e.preventDefault();
      input.style.background = '';
    });
    input.addEventListener('drop', (e) => {
      e.preventDefault();
      input.style.background = '';
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        window.stagedFiles.push(...Array.from(e.dataTransfer.files));
        render();
      }
    });
  }

  window.uploadStagedAttachments = async function (chatId, isRegen) {
    if (isRegen || !window.stagedFiles || window.stagedFiles.length === 0) return [];
    var filesToUpload = Array.prototype.slice.call(window.stagedFiles);
    var formData = new FormData();
    filesToUpload.forEach(function (f) { formData.append('files', f); });
    try {
      var res = await hxFetch(window.api.chatAttachments(chatId), { method: 'POST', body: formData });
      if (res.ok) {
        var data = await res.json();
        if (window.clearUploadedFiles) window.clearUploadedFiles(filesToUpload);
        return data.attachments.map(function (a) { return a.id; });
      }
      console.error('[file-staging] Upload failed with status', res.status);
    } catch (e) {
      console.error('[file-staging] Upload failed', e);
    }
    if (window.clearUploadedFiles) window.clearUploadedFiles(filesToUpload);
    return [];
  };
})();
