(function () {
  // Regex scripts tab (Advanced modal). The list is server-rendered into
  // #regex-scripts-container and rewritten through hxGet so CRUD and ordering
  // have one source of truth; field edits PATCH in place to avoid collapsing
  // the row the user is editing.
  function currentPresetId() {
    return (window.StateManager && StateManager.get('preset_id')) || '';
  }

  // Display transforms are applied server-side, so push each change into the
  // live message list instead of making the user reload the page. The central
  // registry owns the streaming guard; fall back locally when it is absent.
  function refreshDisplayedMessages() {
    if (window.Refresh) {
      Refresh.changed('regex_scripts');
      return;
    }
    if (window.Generation && Generation.isActive && Generation.isActive()) return;
    var chatId = (window.StateManager && StateManager.get('chat_id')) || '';
    if (chatId && window.refreshChatMessages) window.refreshChatMessages(chatId);
  }

  function patchScript(id, patch) {
    return fetch('/api/regex-scripts/' + id, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }).then(function (r) {
      if (!r.ok) {
        return r.json().then(function (e) {
          if (window.showErrorToast) showErrorToast((e && e.detail) || 'Failed to save script');
          throw e;
        });
      }
      return r.json();
    });
  }

  function refreshSingleRegexScript(item) {
    if (!item || !item.dataset.id) return;
    var open = item.classList.contains('expanded') ? '?open=1' : '';
    hxGet('/partials/regex-scripts/item/' + item.dataset.id + open, {
      target: '.regex-item[data-id="' + item.dataset.id + '"]',
      swap: 'outerHTML',
    });
  }

  function saveScript(el, patch) {
    var item = el.closest('.regex-item');
    if (!item) return Promise.resolve();
    return patchScript(item.dataset.id, patch)
      .then(function () {
        refreshSingleRegexScript(item);
        refreshDisplayedMessages();
      })
      .catch(function () {});
  }

  window.reloadRegexScripts = function () {
    var container = document.getElementById('regex-scripts-container');
    if (!container) return Promise.resolve();
    // Keep expanded rows open across the swap.
    var openIds = [];
    container.querySelectorAll('.regex-item.expanded').forEach(function (item) {
      if (item.dataset.id) openIds.push(item.dataset.id);
    });
    var pid = currentPresetId();
    var url = '/partials/regex-scripts' + (pid ? '?preset_id=' + encodeURIComponent(pid) : '');
    return hxGet(url, { target: '#regex-scripts-container', swap: 'innerHTML' }).then(function () {
      openIds.forEach(function (id) {
        var item = container.querySelector('.regex-item[data-id="' + id + '"]');
        if (!item) return;
        var body = item.querySelector('.regex-body');
        var title = item.querySelector('.arranger-title-group');
        if (body) body.style.display = 'flex';
        item.classList.add('expanded');
        if (title) title.setAttribute('aria-expanded', 'true');
      });
      setTimeout(window.initRegexSortables, 30);
    });
  };

  window.initRegexSortables = function () {
    document.querySelectorAll('#regex-scripts-container .regex-sortable').forEach(function (list) {
      if (list._sortable) list._sortable.destroy();
      list._sortable = new Sortable(list, {
        animation: 150,
        ghostClass: 'sortable-ghost',
        handle: '.regex-handle',
        // Each scope sorts within itself only; the global group always runs
        // before the preset group, so cross-list moves would be meaningless.
        group: {
          name: 'regex-' + (list.dataset.scope || '') + '-' + (list.dataset.scopeId || ''),
          pull: false,
          put: false,
        },
        onEnd: function () {
          window.updateRegexPositions();
        },
      });
    });
  };

  window.updateRegexPositions = function () {
    var ids = [];
    document
      .querySelectorAll('#regex-scripts-container .regex-sortable .regex-item')
      .forEach(function (item) {
        ids.push(item.dataset.id);
      });
    var opts = {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: ids }),
    };
    var req = window.Refresh
      ? Refresh.mutate('/api/regex-scripts/reorder', opts, { changed: ['regex_scripts'] })
      : fetch('/api/regex-scripts/reorder', opts);
    req
      .then(function (r) {
        if (!r.ok) throw new Error('reorder failed');
        if (!window.Refresh) refreshDisplayedMessages();
      })
      .catch(function () {
        if (window.showErrorToast) showErrorToast('Could not save script order');
      });
  };

  window.handleRegexUpdate = function (el, patch) {
    saveScript(el, patch);
  };

  window.handleRegexEnabled = function (el) {
    var enabled = !el.classList.contains('active');
    el.classList.toggle('active', enabled);
    saveScript(el, { enabled: enabled });
  };

  window.toggleRegexFlag = function (el) {
    el.classList.toggle('active');
    window.handleRegexFlags(el);
  };

  window.handleRegexFlags = function (el) {
    var item = el.closest('.regex-item');
    if (!item) return;
    var flags = [];
    item.querySelectorAll('.regex-flag').forEach(function (chip) {
      if (chip.classList.contains('active')) flags.push(chip.dataset.flag);
    });
    saveScript(el, { flags: flags.join('') });
  };

  window.toggleRegexPlacement = function (el) {
    el.classList.toggle('active');
    window.handleRegexPlacement(el);
  };

  window.handleRegexPlacement = function (el) {
    var item = el.closest('.regex-item');
    if (!item) return;
    var places = [];
    item.querySelectorAll('.regex-placement').forEach(function (chip) {
      if (chip.classList.contains('active')) places.push(chip.dataset.place);
    });
    saveScript(el, { placement: places.join(',') });
  };

  function toggleRegexToggle(el, field, extra) {
    if (el.disabled) return;
    var patch = {};
    patch[field] = !el.classList.contains('active');
    if (extra) extra(patch);
    saveScript(el, patch);
  }

  window.toggleRegexPrompt = function (el) {
    toggleRegexToggle(el, 'apply_prompt');
  };

  window.toggleRegexDisplay = function (el) {
    toggleRegexToggle(el, 'apply_display');
  };

  window.toggleRegexBlock = function (el) {
    toggleRegexToggle(el, 'as_block', function (patch) {
      if (patch.as_block) patch.apply_display = true;
    });
  };

  window.toggleRegexBody = function (el) {
    var item = el.closest('.regex-item');
    if (!item) return;
    var body = item.querySelector('.regex-body');
    var expanded = body.style.display !== 'none';
    body.style.display = expanded ? 'none' : 'flex';
    item.classList.toggle('expanded', !expanded);
    el.setAttribute('aria-expanded', String(!expanded));
  };

  window.createRegexScript = function (scope, scopeId) {
    fetch('/api/regex-scripts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: scope,
        scope_id: scopeId || null,
        name: 'New script',
        pattern: '',
        replacement: '',
        placement: 'ai',
        apply_prompt: true,
        apply_display: true,
        as_block: false,
      }),
    })
      .then(function (r) {
        if (!r.ok) {
          return r.json().then(function (e) {
            throw e;
          });
        }
        return r.json();
      })
      .then(function () {
        return window.reloadRegexScripts().then(function () {
          var list = document.querySelector(
            '#regex-scripts-container .regex-sortable[data-scope="' + scope + '"]',
          );
          if (!list) return;
          var items = list.querySelectorAll('.regex-item');
          var created = items[items.length - 1];
          if (created) {
            var title = created.querySelector('.arranger-title-group');
            if (title) title.click();
            var patternField = created.querySelector('.regex-pattern');
            if (patternField) patternField.focus();
          }
        });
      })
      .then(function () {
        refreshDisplayedMessages();
      })
      .catch(function (e) {
        if (window.showErrorToast) showErrorToast((e && e.detail) || 'Could not create script');
      });
  };

  window.deleteRegexScript = function (el) {
    var item = el.closest('.regex-item');
    if (!item) return;
    window.openConfirmModal('Delete this regex script?', function () {
      fetch('/api/regex-scripts/' + item.dataset.id, { method: 'DELETE' })
        .then(function (r) {
          if (!r.ok) throw new Error('delete failed');
          window.reloadRegexScripts();
          refreshDisplayedMessages();
        })
        .catch(function () {
          if (window.showErrorToast) showErrorToast('Could not delete script');
        });
    });
  };

  window.previewRegexScript = function (el) {
    var item = el.closest('.regex-item');
    if (!item) return;
    var out = item.querySelector('.regex-preview-out');
    var flags = [];
    item.querySelectorAll('.regex-flag').forEach(function (chip) {
      if (chip.classList.contains('active')) flags.push(chip.dataset.flag);
    });
    fetch('/api/regex-scripts/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        pattern: item.querySelector('.regex-pattern').value,
        replacement: item.querySelector('.regex-replacement').value,
        flags: flags.join(''),
        sample: item.querySelector('.regex-sample').value,
        as_block: item.querySelector('.regex-block').classList.contains('active'),
        name: (item.querySelector('.arranger-input') || {}).value || 'Block',
      }),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok) {
          out.textContent = (res.data && res.data.detail) || 'Invalid pattern';
          out.classList.add('regex-preview-error');
        } else {
          out.textContent = res.data.result;
          out.classList.remove('regex-preview-error');
        }
      })
      .catch(function () {
        out.textContent = 'Preview request failed';
        out.classList.add('regex-preview-error');
      });
  };
})();
