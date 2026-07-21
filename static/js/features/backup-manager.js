(function () {
  if (window.BackupManager) return;

  const M = {};

  function formatBytes(bytes) {
    if (!bytes) return '0 B';
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
    return (bytes / 1073741824).toFixed(1) + ' GB';
  }

  function formatTimestamp(ts) {
    try {
      const [datePart, timePart] = ts.split('T');
      if (!timePart) return ts;
      return new Date(datePart + 'T' + timePart.replace(/-/g, ':')).toLocaleString();
    } catch (_) {
      return ts;
    }
  }

  function setStatus(el, text, isError) {
    if (el) {
      el.textContent = text;
      el.className = isError ? 'text-xs text-red-500 block mt-1' : 'text-xs text-muted block mt-1';
    }
  }

  function toggleActive(el, on) {
    if (!el) return;
    if (on) el.classList.add('active');
    else el.classList.remove('active');
  }

  M.loadList = async function () {
    const list = document.getElementById('backups-list');
    if (!list) return;
    list.innerHTML =
      '<div class="flex justify-center py-6">' + '<div class="message-spinner"></div>' + '</div>';
    try {
      const resp = await fetch(window.api.backups);
      const backups = await resp.json();
      if (!backups.length) {
        list.innerHTML =
          '<div class="flex flex-col items-center gap-2 py-8 text-muted">' +
          '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.4">' +
          '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>' +
          '<path d="M12 10v6"/><path d="M9 13h6"/>' +
          '</svg>' +
          '<span class="text-sm">No backups yet. Create one to safeguard your data.</span>' +
          '</div>';
        return;
      }
      let html = '';
      backups.forEach(function (b) {
        html +=
          '<div class="flex items-center gap-3 p-3 rounded-lg" style="background:var(--surface-2);border:1px solid var(--border);">' +
          '<div class="flex-1 min-w-0">' +
          '<span class="text-sm font-semibold block">' +
          formatTimestamp(b.id) +
          '</span>' +
          '<span class="text-xs" style="color:var(--text-muted);">' +
          formatBytes(b.size_bytes) +
          '</span>' +
          '</div>' +
          '<div class="flex gap-1 shrink-0">' +
          '<button class="btn btn-secondary btn-sm" onclick="BackupManager.restore(\'' +
          b.id +
          '\')">Restore</button>' +
          '<button class="btn btn-danger btn-sm" onclick="BackupManager.delete(\'' +
          b.id +
          '\')">Delete</button>' +
          '</div>' +
          '</div>';
      });
      list.innerHTML = html;
    } catch (_) {
      list.innerHTML =
        '<div class="text-sm text-red-500 text-center py-4">Failed to load backups.</div>';
    }
  };

  M.create = function () {
    const btn = document.getElementById('btn-create-backup');
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    btn.textContent = 'Creating…';
    fetch(window.api.backups, { method: 'POST' })
      .then(() => M.loadList())
      .catch(() => M.loadList())
      .finally(() => {
        btn.disabled = false;
        btn.textContent = 'Create Backup';
      });
  };

  M.restore = function (backupId) {
    window.customConfirm(
      '<div class="text-sm" style="color:var(--text);"><strong>Restore this backup?</strong></div>' +
        '<div class="text-sm mt-2" style="color:var(--text-muted);">All data from the backup will be imported. Existing data is preserved.</div>',
      function () {
        fetch(window.api.backupRestore(backupId), { method: 'POST' })
          .then((r) => r.json())
          .then((d) => {
            if (d.restored) {
              setStatus(document.getElementById('backup-status'), 'Backup restored successfully.');
              M.loadList();
            }
          })
          .catch(() =>
            setStatus(document.getElementById('backup-status'), 'Restore failed.', true),
          );
      },
    );
  };

  M.delete = function (backupId) {
    window.customConfirm(
      '<div class="text-sm" style="color:var(--text);"><strong>Delete this backup?</strong></div>' +
        '<div class="text-sm mt-2" style="color:var(--text-muted);">This cannot be undone.</div>',
      function () {
        fetch(window.api.backupDelete(backupId), { method: 'DELETE' })
          .then(() => M.loadList())
          .catch(() => M.loadList());
      },
    );
  };

  M.importFile = function (input) {
    if (!input.files || !input.files[0]) return;
    const file = input.files[0];
    if (!file.name.endsWith('.focus')) {
      setStatus(document.getElementById('backup-status'), 'Only .focus files are accepted.', true);
      return;
    }
    const fd = new FormData();
    fd.append('file', file);
    const st = document.getElementById('backup-status');
    setStatus(st, 'Importing…');
    fetch(window.api.import_, { method: 'POST', body: fd })
      .then((r) => r.json())
      .then((d) => {
        setStatus(st, 'Imported ' + (d.total_entities || 0) + ' entities.');
        setTimeout(() => {
          location.reload();
        }, 800);
      })
      .catch(() => setStatus(st, 'Import failed.', true))
      .finally(() => {
        input.value = '';
      });
  };

  M._exportState = {
    characters: 'none',
    personas: 'none',
    presets: 'none',
    chats: false,
    providers: false,
    secrets: false,
    selCharacters: {},
    selPersonas: {},
    selPresets: {},
  };

  M.openExportModal = function () {
    ['characters', 'personas', 'presets'].forEach((type) => {
      M._exportState[type] = 'none';
      const capType = type.charAt(0).toUpperCase() + type.slice(1);
      M._exportState['sel' + capType] = {};
    });
    M._exportState.chats = false;
    M._exportState.providers = false;
    M._exportState.secrets = false;
    M._applyExportUI();
    openModal('modal-export');
  };

  M._entitySelectType = null;

  M._applyExportUI = function () {
    const s = M._exportState;
    ['characters', 'personas', 'presets'].forEach((type) => {
      const buttons = document.querySelectorAll('[data-export-btn="' + type + '"]');
      buttons.forEach((btn) => {
        const val = btn.dataset.exportVal;
        toggleActive(btn, val === s[type]);
        if (val === 'some') {
          const capType = type.charAt(0).toUpperCase() + type.slice(1);
          const count = Object.keys(s['sel' + capType] || {}).length;
          btn.textContent = count ? 'Selected (' + count + ')' : 'Select';
        }
      });
    });
    toggleActive(document.getElementById('export-toggle-chats'), !!s.chats);
    toggleActive(document.getElementById('export-toggle-providers'), !!s.providers);
    toggleActive(document.getElementById('export-toggle-secrets'), !!s.secrets);
  };

  M.setExportType = function (type, value) {
    M._exportState[type] = value;
    if (value === 'some') {
      M.openEntitySelect(type);
    } else {
      const capType = type.charAt(0).toUpperCase() + type.slice(1);
      M._exportState['sel' + capType] = {};
      if (M._entitySelectType === type) closeModal('modal-entity-select');
    }
    M._applyExportUI();
  };

  M.toggleExportFlag = function (flag) {
    M._exportState[flag] = !M._exportState[flag];
    M._applyExportUI();
  };

  M.openEntitySelect = function (type) {
    M._entitySelectType = type;
    const title = document.querySelector('#modal-entity-select .modal-title');
    const label =
      type === 'characters' ? 'Characters' : type === 'personas' ? 'Personas' : 'Presets';
    if (title) title.textContent = 'Select ' + label;
    const url = window.api.partials.exportEntities + '?type=' + type;
    htmx.ajax('GET', url, { target: '#entity-select-list', swap: 'innerHTML' }).then(function () {
      M._applyEntitySelection(type);
    });
    openModal('modal-entity-select');
  };

  M.filterExportEntities = function (type, query) {
    if (!type) return;
    const url =
      window.api.partials.exportEntities + '?type=' + type + '&filter=' + encodeURIComponent(query);
    htmx.ajax('GET', url, { target: '#entity-select-list', swap: 'innerHTML' }).then(function () {
      M._applyEntitySelection(type);
    });
  };

  M._applyEntitySelection = function (type) {
    const capType = type.charAt(0).toUpperCase() + type.slice(1);
    const map = M._exportState['sel' + capType] || {};
    const list = document.getElementById('entity-select-list');
    if (!list) return;
    list.querySelectorAll('[data-export-id]').forEach(function (el) {
      const id = el.dataset.exportId;
      const cb = el.querySelector('input[type="checkbox"]');
      if (cb) cb.checked = !!map[id];
    });
  };

  M.toggleExportEntity = function (el, type, id) {
    if (!type && el instanceof Element) {
      type = el.dataset.exportType;
      id = el.dataset.exportId;
    }
    const capType = type.charAt(0).toUpperCase() + type.slice(1);
    const key = 'sel' + capType;
    if (!M._exportState[key]) M._exportState[key] = {};
    if (M._exportState[key][id]) {
      delete M._exportState[key][id];
    } else {
      M._exportState[key][id] = true;
    }
    const cb = el.querySelector('input[type="checkbox"]');
    if (cb) cb.checked = !!M._exportState[key][id];
    M._applyExportUI();
  };

  M.doExport = async function () {
    const btn = document.getElementById('export-download-btn');
    if (!btn) return;
    btn.disabled = true;
    btn.textContent = 'Exporting…';

    const s = M._exportState;
    const body = {};

    for (const type of ['characters', 'personas', 'presets']) {
      const capType = type.charAt(0).toUpperCase() + type.slice(1);
      if (s[type] === 'all') {
        body[type] = ['*'];
      } else if (s[type] === 'some') {
        body[type] = Object.keys(s['sel' + capType] || {});
      } else {
        body[type] = [];
      }
    }

    body.chats = [];
    if (s.chats) {
      try {
        const cr = await fetch('/api/chats/');
        const allChats = await cr.json();
        let charIds = null;
        if (s.characters !== 'some') {
          body.chats = allChats.map((c) => c.id);
        } else {
          charIds = Object.keys(s.selChars || {});
          body.chats = allChats
            .filter((c) => charIds.indexOf(c.character_id) >= 0)
            .map((c) => c.id);
        }
      } catch (_) {}
    }
    body.include_providers = !!s.providers;
    body.include_secrets = !!s.secrets;

    fetch(window.api.export, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((r) => r.blob())
      .then((blob) => {
        const u = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = u;
        a.download = 'focus-export.focus';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(u);
        closeModal('modal-export');
      })
      .catch(() => alert('Export failed.'))
      .finally(() => {
        btn.disabled = false;
        btn.textContent = 'Export';
      });
  };

  M.cleanDatabase = function () {
    window.customConfirm(
      '<div class="text-sm" style="color:var(--text);"><strong>Clean Database?</strong></div>' +
        '<div class="text-sm mt-2" style="color:var(--text-muted);">Permanently deletes trashed characters, chats, and orphaned data. This cannot be undone.</div>',
      function () {
        fetch(window.api.cleanDb, { method: 'POST' })
          .then((r) => r.json())
          .then((d) => {
            const parts = [];
            for (var k in d) parts.push(k + ': ' + d[k]);
            setStatus(document.getElementById('backup-status'), 'Cleaned: ' + parts.join(', '));
          })
          .catch(() => setStatus(document.getElementById('backup-status'), 'Clean failed.', true));
      },
    );
  };

  window.BackupManager = M;
})();
