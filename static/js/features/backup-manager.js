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
      el.className = 'text-xs block mt-1';
      el.style.color = isError ? 'var(--danger)' : 'var(--text-muted)';
    }
  }

  function toggleActive(el, on) {
    if (!el) return;
    if (on) el.classList.add('active');
    else el.classList.remove('active');
  }

  function toastProgress(prefix, event) {
    const label = event.label || 'Working';
    const step = event.total ? ' ' + event.current + '/' + event.total : '';
    return prefix + ' — ' + label + step;
  }

  const COUNT_LABELS = {
    chats: 'chats deleted',
    characters: 'characters deleted',
    personas: 'personas deleted',
    block_images: 'orphaned images',
    attachments: 'detached attachments',
    compressed_purged: 'cached images purged',
    orphaned_entity_dirs: 'orphaned folders',
    orphaned_files: 'orphaned files',
    empty_dirs_removed: 'empty folders',
  };

  function describeCounts(counts) {
    const parts = [];
    if (counts) {
      Object.keys(COUNT_LABELS).forEach(function (key) {
        if (counts[key]) parts.push(counts[key] + ' ' + COUNT_LABELS[key]);
      });
    }
    return parts.length ? ': ' + parts.join(', ') : ' — nothing to remove.';
  }

  M.loadList = async function () {
    const list = document.getElementById('backups-list');
    if (!list) return;
    M.refreshPurgePreview();
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
          '<div class="backup-row">' +
          '<div class="backup-row-main">' +
          '<span class="backup-row-date">' +
          formatTimestamp(b.id) +
          '</span>' +
          '<span class="backup-row-size">' +
          formatBytes(b.size_bytes) +
          '</span>' +
          '</div>' +
          '<div class="backup-row-actions">' +
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
        '<div class="text-sm text-center py-4" style="color:var(--danger)">Failed to load backups.</div>';
    }
  };

  M.create = function () {
    const btn = document.getElementById('btn-create-backup');
    if (!btn || btn.disabled) return;
    btn.disabled = true;
    window.showInfoToast('Creating backup…', { id: 'backup-create', duration: 0 });
    return window
      .streamProgress(window.api.backups, {}, function (event) {
        window.showInfoToast(toastProgress('Creating backup', event), {
          id: 'backup-create',
          duration: 0,
        });
      })
      .then(function (backup) {
        window.hideToast('backup-create');
        window.showSuccessToast('Backup created (' + formatBytes(backup.size_bytes) + ')');
        return M.loadList();
      })
      .catch(function (e) {
        window.hideToast('backup-create');
        window.showErrorToast('Backup failed: ' + e.message);
      })
      .finally(function () {
        btn.disabled = false;
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
              window.showSuccessToast('Backup restored — reloading…');
              setStatus(document.getElementById('backup-status'), 'Backup restored successfully.');
              // A restore can replace arbitrary entities, so a hard reload is the
              // one honest refresh; mirrors the import path.
              setTimeout(() => {
                if (typeof location !== 'undefined') location.reload();
              }, 600);
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
          .then((r) => {
            if (r.ok) window.showSuccessToast('Backup deleted');
            return M.loadList();
          })
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
        window.showSuccessToast('Imported ' + (d.total_entities || 0) + ' entities.');
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
    hxGet(url, { target: '#entity-select-list', swap: 'innerHTML' }).then(function () {
      M._applyEntitySelection(type);
    });
    openModal('modal-entity-select');
  };

  M.filterExportEntities = function (type, query) {
    if (!type) return;
    const url =
      window.api.partials.exportEntities + '?type=' + type + '&filter=' + encodeURIComponent(query);
    hxGet(url, { target: '#entity-select-list', swap: 'innerHTML' }).then(function () {
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
        window.showSuccessToast('Export ready');
      })
      .catch(() => {
        window.showErrorToast('Export failed.');
      })
      .finally(() => {
        btn.disabled = false;
        btn.textContent = 'Export';
      });
  };

  // ── Stale chats → Trash ──
  M._purge = { days: 90, count: 0, reqId: 0 };

  M.setPurgeRange = function (el) {
    const value = el ? el.value : '90';
    const customInput = document.getElementById('purge-days-custom');
    const isCustom = value === 'custom';
    if (customInput) customInput.classList.toggle('hidden', !isCustom);
    M._purge.days = parseInt(isCustom ? customInput && customInput.value : value, 10) || 0;
    M.refreshPurgePreview();
  };

  M.setPurgeCustom = function (el) {
    M._purge.days = parseInt(el.value, 10) || 0;
    M.refreshPurgePreview();
  };

  M.refreshPurgePreview = function () {
    const status = document.getElementById('purge-old-chats-status');
    const btn = document.getElementById('btn-purge-old-chats');
    const days = M._purge.days;
    const reqId = ++M._purge.reqId;
    const span = days === 1 ? '1 day' : days + ' days';

    if (days < 1) {
      M._purge.count = 0;
      if (btn) btn.disabled = true;
      setStatus(status, 'Enter at least 1 day.', true);
      return;
    }

    if (btn) btn.disabled = true;
    setStatus(status, 'Counting…');

    fetch(window.api.chatsStale + '?days=' + days)
      .then((r) => r.json())
      .then((d) => {
        if (reqId !== M._purge.reqId) return;
        M._purge.count = d.count || 0;
        if (btn) btn.disabled = M._purge.count === 0;
        setStatus(
          status,
          M._purge.count
            ? M._purge.count + ' chat' + (M._purge.count === 1 ? '' : 's') + ' older than ' + span
            : 'No chats older than ' + span + '.',
        );
      })
      .catch(() => {
        if (reqId !== M._purge.reqId) return;
        M._purge.count = 0;
        if (btn) btn.disabled = true;
        setStatus(status, 'Failed to count old chats.', true);
      });
  };

  M.purgeOldChats = function () {
    const days = M._purge.days;
    if (days < 1) return;
    const btn = document.getElementById('btn-purge-old-chats');
    if (btn && btn.disabled) return;

    const count = M._purge.count;
    const span = days === 1 ? '1 day' : days + ' days';
    window.customConfirm(
      '<div class="text-sm" style="color:var(--text);"><strong>Move ' +
        count +
        ' ' +
        (count === 1 ? 'chat' : 'chats') +
        ' to Trash?</strong></div>' +
        '<div class="text-sm mt-2" style="color:var(--text-muted);">Chats not updated in the last ' +
        span +
        ' go to the Trash Bin, where each one can be restored. Clean DB deletes them for good.</div>',
      function () {
        if (btn) btn.disabled = true;
        fetch(window.api.chatsStale + '?days=' + days, { method: 'DELETE' })
          .then((r) => (r.ok ? r.json() : Promise.reject(new Error('Purge failed'))))
          .then((d) => {
            window.showSuccessToast(
              d.deleted + ' chat' + (d.deleted === 1 ? '' : 's') + ' moved to Trash',
            );
            const activeId = window.StateManager ? StateManager.get('chat_id') : null;
            if (activeId && (d.ids || []).indexOf(activeId) >= 0) {
              const charId = StateManager.get('character_id');
              window.location.href = charId
                ? '/chat?character_id=' + encodeURIComponent(charId)
                : '/chat';
              return;
            }
            if (window.Refresh) Refresh.changed('chats');
            else if (window._refreshChatList) window._refreshChatList(StateManager.get('chat_id'));
            M.refreshPurgePreview();
          })
          .catch(() => {
            window.showErrorToast('Failed to move old chats to Trash.');
            M.refreshPurgePreview();
          });
      },
    );
  };

  M.cleanDatabase = function (el) {
    window.customConfirm(
      '<div class="text-sm" style="color:var(--text);"><strong>Clean Database?</strong></div>' +
        '<div class="text-sm mt-2" style="color:var(--text-muted);">Permanently deletes trashed characters, chats, and orphaned data. This cannot be undone.</div>',
      function () {
        const btn = el && typeof el.disabled === 'boolean' ? el : null;
        if (btn) btn.disabled = true;
        window.showInfoToast('Cleaning database…', { id: 'clean-db', duration: 0 });
        window
          .streamProgress(window.api.cleanDb, {}, function (event) {
            window.showInfoToast('Cleaning — ' + (event.label || 'working'), {
              id: 'clean-db',
              duration: 0,
            });
          })
          .then(function (counts) {
            window.hideToast('clean-db');
            const detail = describeCounts(counts);
            window.showSuccessToast('Database cleaned' + detail);
            setStatus(document.getElementById('backup-status'), 'Cleaned' + detail);
          })
          .catch(function (e) {
            window.hideToast('clean-db');
            window.showErrorToast('Clean failed: ' + e.message);
            setStatus(document.getElementById('backup-status'), 'Clean failed.', true);
          })
          .finally(function () {
            if (btn) btn.disabled = false;
          });
      },
    );
  };

  window.BackupManager = M;
})();
