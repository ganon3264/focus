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
      el.className =
        'flex items-center gap-1 bg-surface-2 p-1 rounded border border-border text-xs relative group';

      const url = f.type.startsWith('image/') ? URL.createObjectURL(f) : '';

      if (f.type.startsWith('image/')) {
        const thumbnail = window.createMediaThumbnail({
          src: url ? url.replace(/^\/+/, '') : '',
          mimeType: f.type,
          size: 32,
          name: f.name,
          showName: false,
          onClick: null,
          onDelete: function (e) {
            window.removeStagedFile(idx);
          },
        });
        thumbnail.querySelector('img').src = url;
        URL.revokeObjectURL(url);

        var cropBtn = document.createElement('button');
        cropBtn.className =
          'absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-black/70 text-white rounded-full w-6 h-6 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity z-10 hover:bg-black/90';
        cropBtn.innerHTML = window.getSvgSprite('crop', 12);
        cropBtn.title = 'Crop';
        cropBtn.addEventListener('click', function (e) {
          e.stopPropagation();
          window.cropStagedImage(idx);
        });
        thumbnail.querySelector('div') ? thumbnail.querySelector('div').appendChild(cropBtn) : thumbnail.appendChild(cropBtn);

        el.appendChild(thumbnail);
      } else {
        el.innerHTML =
          '<div class="h-8 w-8 bg-surface-3 flex items-center justify-center rounded shrink-0">' +
          window.getSvgSprite('music', 24) +
          '</div>';
      }

      var nameSpan = document.createElement('span');
      nameSpan.className = 'max-w-[100px] truncate';
      nameSpan.title = f.name;
      nameSpan.textContent = f.name;
      el.appendChild(nameSpan);

      var removeBtn = document.createElement('button');
      removeBtn.className =
        'text-danger hover:text-white hover:bg-danger rounded w-5 h-5 flex items-center justify-center ml-1 transition-colors z-20';
      removeBtn.innerHTML = window.getSvgSprite('close', 16);
      removeBtn.title = 'Remove';
      removeBtn.addEventListener('click', function () {
        window.removeStagedFile(idx);
      });
      el.appendChild(removeBtn);

      stagingArea.appendChild(el);
    });

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
      { aspectRatio: NaN },
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
})();
