(function () {
  window.reloadPromptArranger = function (presetId) {
    // The arranger content lives inside a stable #arranger-content wrapper
    // (header hint stays outside it), so reloading only swaps the content.
    if (!document.getElementById('arranger-content')) return Promise.resolve();
    var url = '/partials/prompt-arranger/' + presetId;
    var params = new URLSearchParams();
    if (StateManager.get('character_id'))
      params.append('character_id', StateManager.get('character_id'));
    if (StateManager.get('persona_id'))
      params.append('persona_id', StateManager.get('persona_id'));
    var query = params.toString();
    if (query) url += '?' + query;
    return hxGet(url, { target: '#arranger-content', swap: 'innerHTML' });
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

    // Deferred (non-destructive until Save) attachment/avatar state.
    var workingImages = []; // existing {id,image_path,mime_type} + staged {id,image_path,_file,_objectUrl}
    var removedIds = [];    // persisted image ids marked for deletion on Save
    var pendingAvatar = null; // { blob, objectUrl } staged cropped avatar
    var greetingBaseline = null; // full greeting list captured once after load
    var pendingGreetingOpen = false; // true while the open-load greeting swap is in flight
    var tmpCounter = 0;

    function makeObjectUrl(file) {
      if (typeof URL !== 'undefined' && URL.createObjectURL && file) {
        try { return URL.createObjectURL(file); } catch (e) { return ''; }
      }
      return '';
    }

    function revokeObjectUrl(url) {
      if (url && typeof URL !== 'undefined' && URL.revokeObjectURL) {
        try { URL.revokeObjectURL(url); } catch (e) {}
      }
    }

    // Browsers normalize \r\n/\r to \n in textarea values, while the stored
    // greetings_json keeps them raw — normalize before comparing so plain
    // navigation doesn't show up as an edit.
    function normalizeNewlines(s) {
      return typeof s === 'string' ? s.replace(/\r\n?/g, '\n') : s;
    }

    function setModalDirty(val) {
      if (window.ModalController) ModalController.setDirty(mid, val);
    }

    function setGreetingDirty(val) {
      if (window.ModalController) ModalController.setGreetingDirty(mid, val);
    }

    function renderMedia() {
      var s = sec();
      if (!s) return;
      Array.from(s.querySelectorAll('[data-image-id]')).forEach(function (el) {
        el.remove();
      });
      var addBtn = s.querySelector('.block-media-btn');
      workingImages.forEach(function (m) {
        var div = window.buildMediaThumbnail(
          { id: m.id, image_path: m.image_path, mime_type: m.mime_type },
          function () { window[cfg.deleteFn](m.id); },
          cfg.mediaIdPrefix,
        );
        s.insertBefore(div, addBtn);
      });
      var ph = s.querySelector('.block-media-placeholder');
      if (ph) ph.style.display = workingImages.length ? 'none' : 'block';
    }

    function reloadArrangerIfActive(id) {
      if (!window.StateManager || StateManager.get(cfg.stateKey) !== id || !window.reloadPromptArranger) return;
      var pid = StateManager.get('preset_id');
      if (pid) window.reloadPromptArranger(pid);
    }

    function greetingSection() {
      return document.getElementById(cfg.idPrefix + '-greeting-section');
    }

    function fullGreetingList(section) {
      section = section || greetingSection();
      if (!section) return null;
      var ta = section.querySelector('textarea[name="greeting"]');
      var jsonInput = section.querySelector('input[name="greetings_json"]');
      var idxInput = section.querySelector('input[name="greeting_idx"]');
      var list = [];
      if (jsonInput) {
        try { list = JSON.parse(jsonInput.value || '[]'); } catch (e) { list = []; }
      }
      if (!Array.isArray(list)) list = [];
      list = list.map(normalizeNewlines);
      var idx = idxInput ? parseInt(idxInput.value, 10) : 0;
      if (isNaN(idx) || idx < 0) idx = 0;
      if (ta) {
        var value = normalizeNewlines(ta.value);
        if (value && list.length === 0) list = [value];
        else if (idx < list.length) list[idx] = value;
      }
      return list;
    }

    function updateGreetingDirty(section) {
      if (greetingBaseline === null) return;
      var current = fullGreetingList(section);
      var changed = JSON.stringify(current) !== JSON.stringify(greetingBaseline);
      setGreetingDirty(changed);
    }

    window[cfg.uploadFileFn] = function (file) {
      var id = eid('-id').value;
      if (!id) return;
      var tempId = 'tmp-' + (++tmpCounter);
      var objectUrl = '';
      if (file && file.type && file.type.indexOf('image/') === 0) {
        objectUrl = makeObjectUrl(file);
      }
      workingImages.push({
        id: tempId,
        image_path: objectUrl,
        mime_type: file ? file.type : '',
        _file: file,
        _objectUrl: objectUrl,
      });
      renderMedia();
      setModalDirty(true);
    };

    window[cfg.openFn] = function (btn) {
      var id = btn.dataset[P + 'Id'] || '';
      eid('-id').value = id;
      var name = btn.dataset[P + 'Name'] || '';
      eid('-name').value = name;
      eid('-desc').value = btn.dataset[P + 'Desc'] || '';
      var groupInput = eid('-group');
      if (groupInput) groupInput.value = btn.dataset[P + 'Group'] || '';
      var themeIdInput = eid('-theme-id');
      var themeLabel = eid('-theme-label');
      if (themeIdInput && themeLabel) {
        var tid = btn.dataset[P + 'Theme'] || '';
        themeIdInput.value = tid;
        var theme = window.getTheme ? window.getTheme(tid) : null;
        themeLabel.textContent = theme ? theme.name : 'Inherit (global)';
        themeLabel.classList.toggle('text-muted', !theme);
      }
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

      if (pendingAvatar && pendingAvatar.objectUrl) revokeObjectUrl(pendingAvatar.objectUrl);
      pendingAvatar = null;
      workingImages.forEach(function (m) {
        if (m._objectUrl) revokeObjectUrl(m._objectUrl);
      });
      workingImages = [];
      removedIds = [];
      greetingBaseline = null;
      pendingGreetingOpen = false;

      var list = [];
      try {
        list = JSON.parse(btn.dataset[P + 'Media'] || '[]');
      } catch (e) {
        console.error(e);
      }
      workingImages = list.map(function (img) {
        return { id: img.id, image_path: img.image_path || '', mime_type: img.mime_type || '' };
      });
      renderMedia();

      function finishOpen() {
        window.openModal(mid);
      }

      if (cfg.greetingSectionId) {
        pendingGreetingOpen = true;
        var p = hxPost(cfg.greetingPartial(id), {
          target: '#' + cfg.greetingSectionId,
          swap: 'outerHTML',
        });
        if (p && typeof p.then === 'function') {
          p.then(finishOpen, function () {
            pendingGreetingOpen = false;
            console.error('Failed to load greeting section');
            finishOpen();
          });
        } else {
          finishOpen();
        }
      } else {
        finishOpen();
      }
    };

    window[cfg.uploadFn] = function (input) {
      if (!input.files || !input.files[0]) return;
      window[cfg.uploadFileFn](input.files[0]);
      input.value = '';
    };

    window[cfg.deleteFn] = function (imageId) {
      var idx = -1;
      for (var i = 0; i < workingImages.length; i++) {
        if (workingImages[i].id === imageId) {
          idx = i;
          break;
        }
      }
      if (idx < 0) return;
      var item = workingImages[idx];
      workingImages.splice(idx, 1);
      if (item._objectUrl) revokeObjectUrl(item._objectUrl);
      else if (item.id && String(item.id).indexOf('tmp-') !== 0) removedIds.push(item.id);
      renderMedia();
      setModalDirty(true);
    };

    window[cfg.avatarFn] = function (input) {
      if (!input.files || !input.files[0]) return;
      var id = eid('-id').value;
      if (!id) return;
      openCropModal(input.files[0], function (blob) {
        if (pendingAvatar && pendingAvatar.objectUrl) revokeObjectUrl(pendingAvatar.objectUrl);
        var objectUrl = makeObjectUrl(blob);
        pendingAvatar = { blob: blob, objectUrl: objectUrl };
        var prev = eid('-image-preview');
        var ph = eid('-image-placeholder');
        prev.src = objectUrl;
        prev.style.display = 'block';
        ph.style.display = 'none';
        setModalDirty(true);
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

      var chain = Promise.resolve();
      workingImages.forEach(function (m) {
        if (!m._file) return;
        chain = chain.then(function () {
          var fd = new FormData();
          fd.append('file', m._file);
          return fetch(cfg.apiImages(id), { method: 'POST', body: fd }).then(function (r) {
            if (!r.ok) throw new Error('upload');
            return r.json();
          });
        });
      });

      if (pendingAvatar) {
        chain = chain.then(function () {
          var fd = new FormData();
          fd.append('file', pendingAvatar.blob, 'avatar.webp');
          return fetch(cfg.apiAvatar(id), { method: 'POST', body: fd }).then(function (r) {
            if (!r.ok) throw new Error('avatar');
            return r.json();
          });
        });
      }

      chain = chain.then(function () {
        return Promise.all(
          removedIds.map(function (imgId) {
            return fetch(cfg.apiImage(id, imgId), { method: 'DELETE' });
          }),
        );
      });

      chain = chain.then(function () {
        return fetch(cfg.apiGet(id), {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
        });
      });

      return chain
        .then(function (r) {
          if (!r.ok) return;
          if (pendingAvatar && pendingAvatar.objectUrl) revokeObjectUrl(pendingAvatar.objectUrl);
          pendingAvatar = null;
          window.closeModal(mid, { discard: true });
          window.showSuccessToast(cfg.dataPrefix === 'char' ? 'Character saved' : 'Persona saved');
          if (cfg.dataPrefix === 'char') {
            window.dispatchEvent(new CustomEvent('character-edited', { detail: { id: id } }));
          }
          reloadArrangerIfActive(id);
          if (cfg.cardEndpoint && cfg.gridId) {
            var currentId = StateManager.get(cfg.stateKey) || '';
            var gridEl = document.getElementById(cfg.gridId);
            var compactView = gridEl && gridEl.dataset.view === 'compact';
            var url = cfg.cardEndpoint + id
              + '?current_' + cfg.stateKey + '=' + encodeURIComponent(currentId)
              + '&compact_view=' + (compactView ? 'true' : 'false');
            hxGet(url, {
              target: '#' + (cfg.stateKey === 'character_id' ? 'char' : 'persona') + '-card-' + id,
              swap: 'outerHTML',
            }).then(function () {
              if (cfg.sortStorageKey && cfg.sortFn && window[cfg.sortFn]) {
                var val = localStorage.getItem(cfg.sortStorageKey);
                if (val) window[cfg.sortFn](val);
              }
            });
          }
        })
        .catch(function (err) {
          console.error(err);
          if (window.showErrorToast) window.showErrorToast('Failed to save');
        });
    };

    if (cfg.greetingSectionId) {
      window.actionGreetingInput = function (el) {
        var section = el && el.closest ? el.closest('#' + cfg.idPrefix + '-greeting-section') : null;
        updateGreetingDirty(section);
      };

      document.addEventListener('htmx:afterSwap', function (e) {
        var t = e.detail && e.detail.target;
        if (!t || t.id !== cfg.idPrefix + '-greeting-section') return;
        if (pendingGreetingOpen) {
          pendingGreetingOpen = false;
          greetingBaseline = fullGreetingList();
          return;
        }
        updateGreetingDirty();
      });
    }

    window.setupDropZone(cfg.dropZoneSelector, function (files) {
      files.forEach(window[cfg.uploadFileFn]);
    });
  };
})();
