(function () {
  window.createMediaThumbnail = function (opts) {
    var div = document.createElement('div');
    div.className = 'relative group';
    var size = opts.size || 48;
    Object.assign(div.style, {
      width: size + 'px',
      height: size + 'px',
      borderRadius: '4px',
      overflow: 'hidden',
      border: '1px solid var(--border)',
      flexShrink: '0',
    });
    if (opts.id) div.id = opts.id;

    var isAudio = opts.mimeType && opts.mimeType.startsWith('audio/');

    if (isAudio) {
      div.innerHTML =
        '<div style="width:100%;height:100%;background:var(--surface-3);display:grid;place-items:center;" title="Audio Attachment">' +
        window.getSvgSprite('music', 24) +
        '</div>';
    } else {
      var imgSrc = opts.src ? '/' + opts.src : '';
      var clickAttr = opts.onClick ? 'style="cursor:pointer"' : '';
      div.innerHTML =
        '<img src="' + imgSrc + '"' + clickAttr + ' style="width:100%;height:100%;object-fit:cover;">';
      if (opts.onClick) {
        div.querySelector('img').addEventListener('click', opts.onClick);
      }
    }

    if (opts.onDelete) {
      var btn = document.createElement('button');
      btn.className =
        'absolute top-0 right-0 w-4 h-4 bg-danger text-white text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity z-10';
      btn.type = 'button';
      btn.innerHTML = window.getSvgSprite('close', 12);
      btn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        opts.onDelete(e);
      });
      div.appendChild(btn);
    }

    if (opts.showName && opts.name) {
      var nameEl = document.createElement('span');
      nameEl.className = 'max-w-[100px] truncate text-xs ml-1';
      nameEl.title = opts.name;
      nameEl.textContent = opts.name;
      div.appendChild(nameEl);
    }

    return div;
  };

  window.buildMediaThumbnail = function (img, onDelete, idPrefix) {
    var el = window.createMediaThumbnail({
      src: img.image_path || '',
      mimeType: img.mime_type,
      size: 48,
      id: idPrefix ? idPrefix + '-' + img.id : undefined,
      onDelete: function (e) {
        e.preventDefault();
        e.stopPropagation();
        onDelete(e.target);
      },
    });
    el.dataset.imageId = img.id;
    return el;
  };

  window.setupDropZone = function (el, onDrop) {
    var container = typeof el === 'string' ? document.querySelector(el) : el;
    if (!container || container.dataset.dropReady) return;
    container.dataset.dropReady = 'true';
    container.addEventListener('dragover', function (e) {
      e.preventDefault();
      e.stopPropagation();
      container.classList.add('drag-over');
    });
    container.addEventListener('dragleave', function (e) {
      e.preventDefault();
      e.stopPropagation();
      container.classList.remove('drag-over');
    });
    container.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      container.classList.remove('drag-over');
      if (e.dataTransfer.files && e.dataTransfer.files.length)
        onDrop(Array.from(e.dataTransfer.files));
    });
  };
})();
