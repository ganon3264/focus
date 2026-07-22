(function () {
  window.reloadPromptArranger = function (presetId, targetId) {
    if (!document.getElementById(targetId)) return;
    var url = '/partials/prompt-arranger/' + presetId;
    var params = new URLSearchParams();
    if (StateManager.get('character_id'))
      params.append('character_id', StateManager.get('character_id'));
    if (StateManager.get('persona_id'))
      params.append('persona_id', StateManager.get('persona_id'));
    var query = params.toString();
    if (query) url += '?' + query;
    htmx.ajax('GET', url, { target: '#' + targetId, swap: 'innerHTML' });
  };

  window.getArrangerContainerId = function (presetId) {
    var list = document.getElementById('arranger-list-' + presetId);
    return list && list.parentElement && list.parentElement.id
      ? list.parentElement.id
      : 'arranger-modal-body';
  };

  window.createEditModalHandlers = function (cfg) {
    var P = cfg.dataPrefix;
    var secId = cfg.mediaSectionId;
    var sec = function () {
      return document.getElementById(secId);
    };
    var eid = function (suf) {
      return document.getElementById(cfg.idPrefix + suf);
    };
    var mid = cfg.modalId;

    window[cfg.uploadFileFn] = function (file) {
      var id = eid('-id').value;
      if (!id) return;
      var fd = new FormData();
      fd.append('file', file);
      fetch(cfg.apiImages(id), { method: 'POST', body: fd })
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          var s = sec();
          if (!s) return;
          var div = window.buildMediaThumbnail(
            data,
            function (e) {
              window[cfg.deleteFn](data.id);
            },
            cfg.mediaIdPrefix,
          );
          s.insertBefore(div, s.lastElementChild.previousElementSibling);
          var ph = s.querySelector('.block-media-placeholder');
          if (ph) ph.style.display = 'none';
          if (
            window.StateManager &&
            StateManager.get(cfg.stateKey) === id &&
            window.reloadPromptArranger
          ) {
            var pid =
              StateManager.get('preset_id') ||
              (document.getElementById('prompt-arranger') &&
              document.querySelector('#prompt-arranger .arranger-list')
                ? document
                    .querySelector('#prompt-arranger .arranger-list')
                    .id.replace('arranger-list-', '')
                : null);
            if (pid) window.reloadPromptArranger(pid, 'prompt-arranger');
          }
        });
    };

    window[cfg.openFn] = function (btn) {
      eid('-id').value = btn.dataset[P + 'Id'] || '';
      var name = btn.dataset[P + 'Name'] || '';
      eid('-name').value = name;
      eid('-desc').value = btn.dataset[P + 'Desc'] || '';
      var imgPath = btn.dataset[P + 'Image'];
      var prev = eid('-image-preview');
      var ph = eid('-image-placeholder');
      if (imgPath) {
        prev.src = '/' + imgPath + '?t=' + new Date().getTime();
        prev.style.display = 'block';
        ph.style.display = 'none';
      } else {
        prev.style.display = 'none';
        ph.innerText = name ? name.charAt(0).toUpperCase() : '?';
        ph.style.display = 'block';
      }
      var s = sec();
      Array.from(s.children).forEach(function (el) {
        if (
          !el.classList.contains('block-media-btn') &&
          !el.classList.contains('block-media-placeholder')
        )
          el.remove();
      });
      var phText = s.querySelector('.block-media-placeholder');
      var list = [];
      try {
        list = JSON.parse(btn.dataset[P + 'Media'] || '[]');
      } catch (e) {
        console.error(e);
      }
      if (list.length > 0 && phText) {
        phText.style.display = 'none';
      } else if (list.length === 0 && phText) {
        phText.style.display = 'block';
      }
      list.forEach(function (img) {
        s.insertBefore(
          window.buildMediaThumbnail(
            img,
            function (e) {
              window[cfg.deleteFn](img.id);
            },
            cfg.mediaIdPrefix,
          ),
          s.lastElementChild.previousElementSibling,
        );
      });
      document.getElementById(mid).classList.remove('hidden');
    };

    window[cfg.uploadFn] = function (input) {
      if (!input.files || !input.files[0]) return;
      window[cfg.uploadFileFn](input.files[0]);
      input.value = '';
    };

    window[cfg.deleteFn] = function (imageId) {
      var id = eid('-id').value;
      if (!id) return;
      fetch(cfg.apiImage(id, imageId), { method: 'DELETE' }).then(function (r) {
        if (!r.ok) return;
        var el = document.getElementById(cfg.mediaIdPrefix + '-' + imageId);
        if (el) el.remove();
        if (
          window.StateManager &&
          StateManager.get(cfg.stateKey) === id &&
          window.reloadPromptArranger
        ) {
          var pid =
            StateManager.get('preset_id') ||
            (document.getElementById('prompt-arranger') &&
            document.querySelector('#prompt-arranger .arranger-list')
              ? document
                  .querySelector('#prompt-arranger .arranger-list')
                  .id.replace('arranger-list-', '')
              : null);
          if (pid) window.reloadPromptArranger(pid, 'prompt-arranger');
        }
      });
    };

    window[cfg.avatarFn] = function (input) {
      if (!input.files || !input.files[0]) return;
      var id = eid('-id').value;
      if (!id) return;
      openCropModal(input.files[0], function (blob) {
        var fd = new FormData();
        fd.append('file', blob, 'avatar.png');
        fetch(cfg.apiAvatar(id), { method: 'POST', body: fd })
          .then(function (r) {
            return r.json();
          })
          .then(function (data) {
            var prev = eid('-image-preview');
            var ph = eid('-image-placeholder');
            prev.src = '/' + data.avatar_path + '?t=' + new Date().getTime();
            prev.style.display = 'block';
            ph.style.display = 'none';
          });
      });
      input.value = '';
    };

    window[cfg.submitFn] = function (e) {
      e.preventDefault();
      var id = eid('-id').value;
      if (!id) return;
      var form = window.resolveFormFromEvent(e);
      if (!form) return;
      var data = Object.fromEntries(new FormData(form));
      fetch(cfg.apiGet(id), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
      }).then(async function (r) {
        if (!r.ok) return;
        window.closeModal(mid);
        if (cfg.cardEndpoint && cfg.gridId) {
          var currentId = StateManager.get(cfg.stateKey) || '';
          var gridEl = document.getElementById(cfg.gridId);
          var compactView = gridEl && gridEl.dataset.view === 'compact';
          var url = cfg.cardEndpoint + id
            + '?current_' + cfg.stateKey + '=' + encodeURIComponent(currentId)
            + '&compact_view=' + (compactView ? 'true' : 'false');
          htmx.ajax('GET', url, {
            target: '#' + (cfg.stateKey === 'character_id' ? 'char' : 'persona') + '-card-' + id,
            swap: 'outerHTML',
          }).then(function () {
            if (cfg.sortStorageKey && cfg.sortFn && window[cfg.sortFn]) {
              var val = localStorage.getItem(cfg.sortStorageKey);
              if (val) window[cfg.sortFn](val);
            }
          });
        }
      });
    };

    window.setupDropZone(cfg.dropZoneSelector, function (files) {
      files.forEach(window[cfg.uploadFileFn]);
    });
  };
})();
