(function () {
  // Presets: the sidebar readout, the collection modal, and the one naming
  // dialog that create / rename / duplicate share.
  //
  // The selector is a readout that opens the collection; every write declares
  // the resource it touched and lets the Refresh registry decide what re-renders
  // (the list, the sidebar readout, the message list).
  //
  // Lives here rather than in the template so it binds once, instead of being
  // re-executed on every htmx swap of #preset-selector.

  var NAME_MODES = {
    new: { title: 'New Preset', verb: 'Create', intent: 'btn create', placeholder: 'e.g. General 1.2' },
    rename: { title: 'Rename Preset', verb: 'Save', intent: 'btn primary', placeholder: '' },
    duplicate: { title: 'Duplicate Preset', verb: 'Duplicate', intent: 'btn create', placeholder: '' },
  };

  function chatId() {
    return window.StateManager ? StateManager.get('chat_id') : null;
  }

  function changed() {
    if (window.Refresh) return Refresh.changed('presets');
  }

  function reloadPresetsModal() {
    return hxGet(api.partials.presetsModal + '?chat_id=' + encodeURIComponent(chatId() || ''), {
      target: '#presets-modal-body-inner',
      swap: 'innerHTML',
    });
  }

  window.reloadPresetsModal = reloadPresetsModal;

  window.actionOpenPresetsModal = function () {
    openModal('modal-presets');
  };

  window.actionSelectPreset = function (el) {
    var id = el.dataset.presetId || null;
    var name = el.dataset.presetName || null;
    closeModal('modal-presets');
    window.applyPreset(id, name);
  };

  // ── The naming dialog ─────────────────────────────────────────────────────
  function openNameModal(mode, preset) {
    var cfg = NAME_MODES[mode];
    var form = document.getElementById('preset-name-form');
    var input = document.getElementById('preset-name-input');
    var submit = document.getElementById('preset-name-submit');
    var title = document.querySelector('#modal-preset-name [data-ui="modal-title"]');
    if (!form || !input || !submit || !title) return;

    form.dataset.mode = mode;
    form.dataset.presetId = (preset && preset.id) || '';
    input.value = (preset && preset.name) || '';
    input.placeholder = cfg.placeholder;
    title.textContent = cfg.title;
    submit.textContent = cfg.verb;
    submit.className = cfg.intent;

    openModal('modal-preset-name');
    setTimeout(function () {
      input.focus();
      input.select();
    }, 0);
  }

  window.actionOpenNewPreset = function () {
    openNameModal('new');
  };

  window.actionRenamePreset = function (el) {
    var row = el.closest('[data-preset-id]');
    if (!row) return;
    openNameModal('rename', { id: row.dataset.presetId, name: row.dataset.presetName });
  };

  window.actionDuplicatePreset = function (el) {
    var row = el.closest('[data-preset-id]');
    if (!row) return;
    openNameModal('duplicate', {
      id: row.dataset.presetId,
      name: row.dataset.presetName + ' Copy',
    });
  };

  window.actionSubmitPresetName = function (form, e) {
    e.preventDefault();
    var mode = form.dataset.mode || 'new';
    var presetId = form.dataset.presetId || '';
    var name = (document.getElementById('preset-name-input').value || '').trim();
    if (!name) return;
    if (mode !== 'new' && !presetId) return;

    var url = api.presets;
    var opts = { method: 'POST' };
    if (mode === 'new') {
      var body = new FormData();
      body.append('name', name);
      opts.body = body;
    } else {
      url = mode === 'rename' ? api.preset(presetId) : api.presetDuplicate(presetId);
      opts = jsonOpts(mode === 'rename' ? 'PATCH' : 'POST', { name: name });
    }

    hxFetch(url, opts)
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return mode === 'rename' ? null : res.json();
      })
      .then(function (data) {
        closeModal('modal-preset-name', { discard: true });
        if (mode === 'new' || mode === 'duplicate') {
          // Creating a preset is a selection: land on the one you just made.
          window.applyPreset(data.id, name);
          window.showSuccessToast(mode === 'new' ? 'Preset created' : 'Preset duplicated');
        } else {
          changed();
          window.showSuccessToast('Preset renamed');
        }
      })
      .catch(function () {
        window.showErrorToast('Could not save the preset');
      });
  };

  // ── Delete ────────────────────────────────────────────────────────────────
  function fallbackRow(deletedId) {
    var rows = document.querySelectorAll('#presets-grid [data-preset-id]');
    for (var i = 0; i < rows.length; i++) {
      if (rows[i].dataset.presetId !== deletedId) return rows[i];
    }
    return null;
  }

  window.actionDeletePreset = function (el) {
    var row = el.closest('[data-preset-id]');
    if (!row) return;
    var id = row.dataset.presetId;
    var name = (row.dataset.presetName || '').replace(/</g, '&lt;');
    var wasActive = window.StateManager && StateManager.get('preset_id') === id;
    var fallback = fallbackRow(id);

    window.customConfirm('Delete preset “' + name + '”?', function () {
      hxFetch(api.preset(id), { method: 'DELETE' })
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          if (wasActive) {
            // Never leave the chat pointing at a preset that no longer exists.
            window.applyPreset(
              fallback ? fallback.dataset.presetId : null,
              fallback ? fallback.dataset.presetName : null,
            );
          } else {
            changed();
          }
          window.showSuccessToast('Preset deleted');
        })
        .catch(function () {
          window.showErrorToast('Could not delete the preset');
        });
    });
  };

  // ── Import ────────────────────────────────────────────────────────────────
  window.importPreset = function (e) {
    e.preventDefault();
    var form = e.target;
    var file = form.querySelector('input[type="file"]').files[0];
    if (!file) return;
    var body = new FormData();
    body.append('file', file);
    hxFetch(api.presetImport, { method: 'POST', body: body })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.id) return;
        window.applyPreset(data.id, data.name || null);
        window.showSuccessToast('Preset imported');
      })
      .catch(function () {
        window.showErrorToast('Import failed — is this a preset file?');
      });
  };
})();
