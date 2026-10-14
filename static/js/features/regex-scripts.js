(function () {
  // Regex scripts tab (Advanced modal). The list is server-rendered into
  // #regex-scripts-container and rewritten through hxGet so CRUD and ordering
  // have one source of truth; field edits PATCH in place to avoid collapsing
  // the row the user is editing.
  function currentPresetId() {
    return (window.StateManager && StateManager.get('preset_id')) || '';
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

  window.reloadRegexScripts = function () {
    var container = document.getElementById('regex-scripts-container');
    if (!container) return Promise.resolve();
    var pid = currentPresetId();
    var url = '/partials/regex-scripts' + (pid ? '?preset_id=' + encodeURIComponent(pid) : '');
    return hxGet(url, { target: '#regex-scripts-container', swap: 'innerHTML' }).then(function () {
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
    fetch('/api/regex-scripts/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: ids }),
    });
  };

  window.handleRegexUpdate = function (el, patch) {
    var item = el.closest('.regex-item');
    if (!item) return;
    patchScript(item.dataset.id, patch).catch(function () {});
  };

  window.handleRegexEnabled = function (el) {
    var item = el.closest('.regex-item');
    if (!item) return;
    var enabled = !el.classList.contains('active');
    el.classList.toggle('active', enabled);
    patchScript(item.dataset.id, { enabled: enabled }).catch(function () {});
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
    patchScript(item.dataset.id, { flags: flags.join('') }).catch(function () {});
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
    patchScript(item.dataset.id, { placement: places.join(',') }).catch(function () {});
  };

  window.setRegexMode = function (el) {
    var item = el.closest('.regex-item');
    if (!item) return;
    item.querySelectorAll('.regex-mode').forEach(function (chip) {
      chip.classList.toggle('active', chip === el);
    });
    patchScript(item.dataset.id, { destination: el.dataset.mode }).catch(function () {});
  };

  window.toggleRegexBody = function (el) {
    var item = el.closest('.regex-item');
    if (!item) return;
    var body = item.querySelector('.regex-body');
    var expanded = body.style.display !== 'none';
    body.style.display = expanded ? 'none' : 'block';
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
        destination: 'ephemeral',
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
      .catch(function (e) {
        if (window.showErrorToast) showErrorToast((e && e.detail) || 'Could not create script');
      });
  };

  window.deleteRegexScript = function (el) {
    var item = el.closest('.regex-item');
    if (!item) return;
    fetch('/api/regex-scripts/' + item.dataset.id, { method: 'DELETE' }).then(function () {
      window.reloadRegexScripts();
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
      });
  };
})();
