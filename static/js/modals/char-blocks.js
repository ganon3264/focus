(function () {
  // Custom character blocks modal. The list is server-rendered and rewritten
  // through hxGet (one source of truth for CRUD + ordering); a field edit
  // PATCHes in place and only the edited row is swapped, so an open block stays
  // open and the pointer keeps its place. Every change saves immediately —
  // there is no Save verb here, the blocks belong to the character.
  function modal() {
    return document.getElementById('modal-char-blocks');
  }

  function charId() {
    var m = modal();
    return (m && m.dataset.charId) || '';
  }

  function container() {
    return document.getElementById('char-blocks-container');
  }

  function itemOf(el) {
    return el && el.closest ? el.closest('[data-ui="char-block"]') : null;
  }

  // The swap lands after hxGet resolves and Alpine then boots the new subtree,
  // so the freshly created row's field may not exist on the first tick.
  function focusBlockName(blockId) {
    var tries = 0;
    (function attempt() {
      var field = document.querySelector(
        '[data-ui="char-block"][data-block-id="' + blockId + '"] [data-ui="char-block-name"]',
      );
      if (field) {
        field.focus();
        if (field.select) field.select();
        return;
      }
      if (++tries < 15) setTimeout(attempt, 40);
    })();
  }

  function fail(message) {
    if (window.showErrorToast) showErrorToast(message);
  }

  // The editor's nav row reads the same count the modal shows, so a block added
  // in the modal is reflected the moment the user closes it.
  function syncCount() {
    var list = container();
    var owner = document.querySelector('#modal-edit-character [data-ui="char-block-count"]');
    if (!list || !owner) return;
    owner.textContent = list.querySelectorAll('[data-ui="char-block"]').length;
  }

  function initSortable() {
    var list = container() && container().querySelector('[data-ui="char-blocks-sortable"]');
    if (!list) return;
    if (list._sortable) list._sortable.destroy();
    list._sortable = new Sortable(list, {
      animation: 150,
      ghostClass: 'sortable-ghost',
      handle: '.char-block-handle',
      onEnd: function () {
        saveOrder();
      },
    });
  }

  function saveOrder() {
    var id = charId();
    var list = container() && container().querySelector('[data-ui="char-blocks-sortable"]');
    if (!id || !list) return;
    var ids = [];
    list.querySelectorAll('[data-ui="char-block"]').forEach(function (block) {
      ids.push(block.dataset.blockId);
    });
    hxJson(api.charBlocksReorder(id), 'POST', { ids: ids })
      .then(function (r) {
        if (!r.ok) throw new Error('reorder failed');
      })
      .catch(function () {
        fail('Could not save block order');
      });
  }

  window.reloadCharBlocks = function () {
    var id = charId();
    if (!id || !container()) return Promise.resolve();
    return hxGet(api.charBlocksPartial(id), {
      target: '#char-blocks-container',
      swap: 'innerHTML',
    }).catch(function () {
      fail('Could not load character blocks');
    });
  };

  // The list is re-rendered by htmx, so the sortable and the count are wired
  // after the swap — never from the hxGet promise, which resolves before it.
  document.addEventListener('htmx:afterSwap', function (e) {
    var target = e.detail && e.detail.target;
    if (!target || target.id !== 'char-blocks-container') return;
    initSortable();
    syncCount();
  });

  function refreshCharBlock(item) {
    var id = charId();
    if (!id || !item) return Promise.resolve();
    return hxGet(api.charBlockPartial(id, item.dataset.blockId), {
      target: '[data-ui="char-block"][data-block-id="' + item.dataset.blockId + '"]',
      swap: 'outerHTML',
    }).catch(function () {});
  }

  function patchBlock(item, patch) {
    var id = charId();
    if (!id || !item) return Promise.reject(new Error('no block'));
    return hxJson(api.charBlock(id, item.dataset.blockId), 'PATCH', patch)
      .then(function (r) {
        if (!r.ok) throw new Error('save failed');
        return r.json();
      })
      .catch(function (err) {
        fail('Could not save block');
        throw err;
      });
  }

  window.actionOpenCharBlocks = function () {
    var idInput = document.getElementById('edit-char-id');
    var m = modal();
    if (!m || !idInput || !idInput.value) return;
    m.dataset.charId = idInput.value;
    window.openModal('modal-char-blocks');
  };

  window.actionAddCharBlock = function () {
    var id = charId();
    if (!id) return;
    var createdId = '';
    hxJson(api.charBlocks(id), 'POST', { name: 'New Block', content: '', role: 'system' })
      .then(function (r) {
        if (!r.ok) throw new Error('create failed');
        return r.json();
      })
      .then(function (data) {
        createdId = (data && data.id) || '';
        // A fresh block opens on arrival: its empty content is the whole point
        // of having created it.
        if (createdId && !expandGet('charBlocks', createdId)) {
          expandToggle('charBlocks', createdId);
        }
        return window.reloadCharBlocks();
      })
      .then(function () {
        focusBlockName(createdId);
      })
      .catch(function () {
        fail('Could not create block');
      });
  };

  window.actionRenameCharBlock = function (el) {
    var item = itemOf(el);
    if (item) patchBlock(item, { name: el.value });
  };

  window.actionSetCharBlockContent = function (el) {
    var item = itemOf(el);
    if (item) patchBlock(item, { content: el.value });
  };

  // Role is the row's own left edge, so the row has to re-render, not just the
  // hidden input.
  window.actionSetCharBlockRole = function (el) {
    var item = itemOf(el);
    if (!item) return;
    patchBlock(item, { role: el.value }).then(function () {
      refreshCharBlock(item);
    }, function () {});
  };

  window.actionToggleCharBlock = function (el) {
    var item = itemOf(el);
    if (!item) return;
    var enabled = !el.classList.contains('active');
    el.classList.toggle('active', enabled);
    item.classList.toggle('disabled', !enabled);
    patchBlock(item, { enabled: enabled }).catch(function () {
      el.classList.toggle('active', !enabled);
      item.classList.toggle('disabled', enabled);
    });
  };

  window.actionDeleteCharBlock = function (el) {
    var item = itemOf(el);
    var id = charId();
    if (!item || !id) return;
    window.customConfirm('Delete this block?', function () {
      hxFetch(api.charBlock(id, item.dataset.blockId), { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) throw new Error('delete failed');
          return window.reloadCharBlocks();
        })
        .catch(function () {
          fail('Could not delete block');
        });
    });
  };

  window.actionUploadCharBlockMedia = function (input) {
    var item = itemOf(input);
    var id = charId();
    if (!item || !id || !input.files || !input.files[0]) return;
    var form = new FormData();
    form.append('file', input.files[0]);
    input.value = '';
    hxFetch(api.charBlockImages(id, item.dataset.blockId), { method: 'POST', body: form })
      .then(function (r) {
        if (!r.ok) throw new Error('upload failed');
        return refreshCharBlock(item);
      })
      .catch(function () {
        fail('Could not upload media');
      });
  };

  window.actionDeleteCharBlockMedia = function (el) {
    var item = itemOf(el);
    var id = charId();
    var thumb = el.closest('[data-image-id]');
    if (!item || !id || !thumb) return;
    hxFetch(api.charBlockImage(id, item.dataset.blockId, thumb.dataset.imageId), {
      method: 'DELETE',
    })
      .then(function (r) {
        if (!r.ok) throw new Error('delete failed');
        return refreshCharBlock(item);
      })
      .catch(function () {
        fail('Could not remove media');
      });
  };

  ModalController.onOpen('modal-char-blocks', function () {
    window.reloadCharBlocks();
  });
})();
