// File staging area: drag/paste/upload, preview rendering, crop.
// Depends on window.getSvgSprite, window.openCropModal

(function(){
  window.stagedFiles = [];

  const fileUpload = document.getElementById('file-upload');
  const stagingArea = document.getElementById('staging-area');
  const input = document.getElementById('chat-input');

  function render() {
    if (!stagingArea) return;
    stagingArea.innerHTML = '';
    window.stagedFiles.forEach((f, idx) => {
      const el = document.createElement('div');
      el.className = 'flex items-center gap-1 bg-surface-2 p-1 rounded border border-border text-xs relative group';

      let preview = '';
      if (f.type.startsWith('image/')) {
        const url = URL.createObjectURL(f);
        const cropBtn = `<button class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-black/70 text-white rounded-full w-6 h-6 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity z-10 hover:bg-black/90" onclick="window.cropStagedImage(${idx})" title="Crop">${window.getSvgSprite('crop', 12)}</button>`;

        preview = `
          <div class="relative h-8 w-8 flex-shrink-0">
            <img src="${url}" class="h-full w-full object-cover rounded" onload="try{URL.revokeObjectURL(this.src)}catch(e){}">
            ${cropBtn}
          </div>
        `;
      } else {
        preview = `<div class="h-8 w-8 bg-surface-3 flex items-center justify-center rounded flex-shrink-0">${window.getSvgSprite('music', 24)}</div>`;
      }

      el.innerHTML = `
        ${preview}
        <span class="max-w-[100px] truncate" title="${f.name}">${f.name}</span>
        <button class="text-danger hover:text-white hover:bg-danger rounded w-5 h-5 flex items-center justify-center ml-1 transition-colors z-20" onclick="window.removeStagedFile(${idx})" title="Remove">${window.getSvgSprite('close', 16)}</button>
      `;
      stagingArea.appendChild(el);
    });

    if (typeof updateSendButtonState === 'function') {
      updateSendButtonState();
    }
  }

  window.removeStagedFile = function(idx) {
    window.stagedFiles.splice(idx, 1);
    render();
  };

  window.cropStagedImage = function(idx) {
    const file = window.stagedFiles[idx];
    if (!file || !file.type.startsWith('image/')) return;
    if (typeof openCropModal !== 'function') return;

    openCropModal(file, (croppedBlob) => {
      const newFile = new File([croppedBlob], file.name, { type: 'image/png' });
      window.stagedFiles[idx] = newFile;
      render();
    }, { aspectRatio: NaN });
  };

  window.clearUploadedFiles = function(uploadedFiles) {
    window.stagedFiles = window.stagedFiles.filter(f => !uploadedFiles.includes(f));
    render();
  };

  if (fileUpload) {
    fileUpload.addEventListener('change', function(e) {
      if (e.target.files.length) {
        window.stagedFiles.push(...Array.from(e.target.files));
        render();
        e.target.value = '';
      }
    });
  }

  window.addEventListener('paste', e => {
    if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length > 0) {
      const newFiles = Array.from(e.clipboardData.files).filter(f => f.type.startsWith('image/'));
      if (newFiles.length > 0) {
        window.stagedFiles.push(...newFiles);
        render();
        e.preventDefault();
      }
    }
  });

  if (input) {
    input.addEventListener('dragover', e => { e.preventDefault(); input.style.background = 'var(--surface-3)'; });
    input.addEventListener('dragleave', e => { e.preventDefault(); input.style.background = ''; });
    input.addEventListener('drop', e => {
      e.preventDefault();
      input.style.background = '';
      if (e.dataTransfer.files && e.dataTransfer.files.length) {
        window.stagedFiles.push(...Array.from(e.dataTransfer.files));
        render();
      }
    });
  }
})();
