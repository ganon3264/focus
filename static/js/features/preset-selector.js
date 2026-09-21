(function () {
  // Preset dropdown actions (duplicate / rename / delete / import / created).
  // Lives here rather than in the template so it binds once, instead of being
  // re-executed on every htmx swap of #preset-selector.
  // Apply/selection helpers stay in core/selection.js.

  window.openDuplicateModal = function (btn) {
    var item = btn.closest('[data-preset-id]');
    var selectorState = Alpine.$data(document.getElementById('preset-selector-wrapper'));
    selectorState.open = false;
    var modalState = Alpine.$data(document.getElementById('dup-preset-form'));
    modalState.dupSourceId = item.dataset.presetId;
    modalState.dupValue = item.querySelector('.preset-item-name').textContent + ' Copy';
    window.openModal('modal-dup-preset');
  };

  window.confirmDuplicate = function () {
    var modalState = Alpine.$data(document.getElementById('dup-preset-form'));
    var sourceId = modalState.dupSourceId;
    var newName = modalState.dupValue;
    if (!sourceId || !newName || !newName.trim()) return;
    var trimmed = newName.trim();
    fetch('/api/presets/' + sourceId + '/duplicate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: trimmed }),
    })
      .then(function (r) {
        if (!r.ok) {
          window.showErrorToast('Failed to duplicate preset');
          throw new Error('duplicate failed');
        }
        return r.json();
      })
      .then(function (data) {
        if (data && data.id) {
          window.closeModal('modal-dup-preset', { discard: true });
          window.applyPreset(data.id);
          window.showSuccessToast('Preset duplicated');
        }
      })
      .catch(function () {});
  };

  window.openRenameModal = function (btn) {
    var item = btn.closest('[data-preset-id]');
    var selectorState = Alpine.$data(document.getElementById('preset-selector-wrapper'));
    selectorState.open = false;
    var modalState = Alpine.$data(document.getElementById('rename-preset-form'));
    modalState.renameTargetId = item.dataset.presetId;
    modalState.renameValue = item.querySelector('.preset-item-name').textContent;
    document.getElementById('rename-preset-form').dataset.renameOriginal = modalState.renameValue;
    window.openModal('modal-rename-preset');
  };

  window.handlePresetCreated = function (evt) {
    try {
      var data = JSON.parse(evt.detail.xhr.response);
      window.applyPreset(data.id);
    } catch (e) {
      window.location.reload();
    }
  };

  window.confirmRename = function () {
    var modalState = Alpine.$data(document.getElementById('rename-preset-form'));
    var pid = modalState.renameTargetId;
    var newName = modalState.renameValue;
    if (!pid || !newName || !newName.trim()) return;
    var trimmed = newName.trim();
    fetch('/api/presets/' + pid, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: trimmed }),
    }).then(function (r) {
      if (r.ok) {
        window.closeModal('modal-rename-preset', { discard: true });
        var state = Alpine.$data(document.getElementById('preset-selector-wrapper'));
        document
          .querySelectorAll('#preset-selector-wrapper [data-preset-id="' + pid + '"]')
          .forEach(function (el) {
            var nameSpan = el.querySelector('.preset-item-name');
            if (nameSpan) nameSpan.textContent = trimmed;
          });
        if (state.selectedId === pid) {
          state.selectedName = trimmed;
        }
        window.showSuccessToast('Preset renamed');
      } else {
        window.showErrorToast('Failed to rename preset');
      }
    });
  };

  window.importPreset = function (file) {
    if (!file) return;
    var formData = new FormData();
    formData.append('file', file);
    fetch('/api/presets/import', { method: 'POST', body: formData })
      .then(function (r) {
        if (r.ok) return r.json();
        else r.text().then(function (t) { window.showErrorToast('Import failed: ' + t); });
      })
      .then(function (data) {
        if (data && data.id) {
          window.showSuccessToast('Preset imported');
          window.applyPreset(data.id);
        }
      });
  };

  window.deletePresetById = function (id) {
    var fallbackItem = null;
    var items = document.querySelectorAll('#preset-selector-wrapper [data-preset-id]');
    for (var i = 0; i < items.length; i++) {
      if (items[i].dataset.presetId && items[i].dataset.presetId !== id) {
        fallbackItem = items[i];
        break;
      }
    }
    window.customConfirm('Delete this preset?', function () {
      fetch('/api/presets/' + id, { method: 'DELETE' }).then(function (r) {
        if (!r.ok) {
          window.showErrorToast('Failed to delete preset');
          return;
        }
        var state = Alpine.$data(document.getElementById('preset-selector-wrapper'));
        if (state.selectedId === id) {
          var fallbackId = fallbackItem ? fallbackItem.dataset.presetId : null;
          window.applyPreset(fallbackId);
        } else {
          window.refreshPresetList();
        }
        window.showSuccessToast('Preset deleted');
      });
    });
  };
})();
