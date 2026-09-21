(function () {
  // Preset variable editing: sortable option lists, the per-group refresh
  // helpers, and the option editor modal. Rendered by
  // presets/preset-variables.html, which calls initVarSortables on each swap.
  var _currentVarBlockId = null;
  var _currentPresetId = null;

  window.updateVarPositions = function (presetId) {
    let pos = -1000;
    const updates = [];
    document
      .querySelectorAll(`#preset-variables-sortable-${presetId} .sortable-var-options`)
      .forEach((groupBody) => {
        groupBody.querySelectorAll('.var-option-item').forEach((opt) => {
          updates.push({ id: opt.dataset.id, position: pos++ });
        });
      });

    fetch(`/api/presets/${presetId}/blocks`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ blocks: updates }),
    });
  };

  window.initVarSortables = function (presetId) {
    const groupContainer = document.getElementById('preset-variables-sortable-' + presetId);
    if (groupContainer) {
      if (groupContainer._sortable) groupContainer._sortable.destroy();
      groupContainer._sortable = new Sortable(groupContainer, {
        animation: 150,
        ghostClass: 'sortable-ghost',
        handle: '.arranger-header',
        onEnd: () => window.updateVarPositions(presetId),
      });

      groupContainer.querySelectorAll('.sortable-var-options').forEach((optContainer) => {
        if (optContainer._sortable) optContainer._sortable.destroy();
        optContainer._sortable = new Sortable(optContainer, {
          animation: 150,
          ghostClass: 'sortable-ghost',
          onEnd: () => window.updateVarPositions(presetId),
        });
      });
    }
  };

  window.reloadPresetVariables = function (presetId) {
    hxGet('/partials/preset-variables/' + presetId, {
      target: '#preset-variables-container-' + presetId,
      swap: 'outerHTML',
    }).then(() => setTimeout(() => window.initVarSortables(presetId), 50));
  };

  window.refreshSingleVarGroup = function (presetId, groupName) {
    var sel = '.var-group-container[data-group-name="' + CSS.escape(groupName) + '"]';
    if (!document.querySelector(sel)) return;
    hxGet('/partials/preset-variables/' + presetId + '/group/' + encodeURIComponent(groupName), {
      target: sel,
      swap: 'outerHTML',
    }).then(function () {
      var group = document.querySelector(sel);
      if (group && !group.querySelector('.var-option-item')) {
        group.remove();
        group = null;
      }
      if (!group) {
        var outer = document.getElementById('preset-variables-container-' + presetId);
        if (outer && !outer.querySelector('.var-group-container')) {
          var sortable = outer.querySelector('.flex.flex-col.gap-2');
          if (sortable) sortable.innerHTML = '<div class="text-muted text-sm mb-2">No variables configured.</div>';
        }
      }
      setTimeout(function () { window.initVarSortables(presetId); }, 50);
    });
  };

  window.handleVarUpdate = function (el) {
    const presetId = el.closest('[data-preset-id]').dataset.presetId;
    const blockId = el.dataset.varId;
    const payload = { enabled: el.classList.contains('active') ? 0 : 1 };
    fetch(`/api/presets/${presetId}/blocks/${blockId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }).then(function () {
      var idsEl = document.querySelector('.var-group-ids[data-ids*="' + blockId + '"]');
      if (idsEl) {
        var container = idsEl.closest('.var-group-container');
        if (container) {
          var gname = container.getAttribute('data-group-name');
          if (gname) {
            window.refreshSingleVarGroup(presetId, gname);
            return;
          }
        }
      }
      window.reloadPresetVariables(presetId);
    });
  };

  window.handleVarDelete = function (el) {
    const presetId = el.closest('[data-preset-id]').dataset.presetId;
    const blockId = el.dataset.varId;
    fetch(`/api/presets/${presetId}/blocks/${blockId}`, {
      method: 'DELETE',
    }).then(function () {
      var idsEl = document.querySelector('.var-group-ids[data-ids*="' + blockId + '"]');
      if (idsEl) {
        var container = idsEl.closest('.var-group-container');
        if (container) {
          var gname = container.getAttribute('data-group-name');
          if (gname) {
            window.refreshSingleVarGroup(presetId, gname);
            return;
          }
        }
      }
      window.reloadPresetVariables(presetId);
    });
  };

  window.openVarEditModal = function (el) {
    const presetId =
      el.dataset.presetId ||
      (el.closest('[data-preset-id]') ? el.closest('[data-preset-id]').dataset.presetId : null);
    const blockId = el.dataset.varId || null;
    const groupName = el.dataset.varName || '';
    const optionLabel = el.dataset.varLabel || '';
    _currentVarBlockId = blockId;
    _currentPresetId = presetId;
    document.querySelector('#var-edit-modal .modal-title').innerText = blockId
      ? 'Edit Variable Option'
      : 'Add New Variable Option';
    document.getElementById('var-modal-group').value = groupName || '';
    document.getElementById('var-modal-label').value = optionLabel || '';
    document.getElementById('var-modal-content').value = '';
    if (blockId) {
      fetch('/api/presets/' + presetId + '/blocks/' + blockId)
        .then(function (r) {
          return r.json();
        })
        .then(function (data) {
          document.getElementById('var-modal-content').value = data.content || '';
          window.openModal('var-edit-modal');
        });
    } else {
      window.openModal('var-edit-modal');
    }
  };

  window.saveVarModal = function () {
    if (!_currentPresetId) return;
    const group = document.getElementById('var-modal-group').value.trim() || 'Variable';
    const label = document.getElementById('var-modal-label').value.trim() || 'Option';
    const content = document.getElementById('var-modal-content').value;
    const combinedName = group + ':' + label;
    const presetId = _currentPresetId;
    const varBlockId = _currentVarBlockId;

    if (varBlockId) {
      fetch('/api/presets/' + presetId + '/blocks/' + varBlockId, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: combinedName, content: content }),
      }).then(function () {
        window.closeModal('var-edit-modal', { discard: true });
        window.refreshSingleVarGroup(presetId, group);
      });
    } else {
      fetch('/api/presets/' + presetId + '/blocks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: combinedName,
          block_type: 'variable',
          content: content,
          role: 'system',
        }),
      }).then(function () {
        window.closeModal('var-edit-modal', { discard: true });
        window.reloadPresetVariables(presetId);
      });
    }
  };
})();
