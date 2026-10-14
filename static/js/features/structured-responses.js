(function () {
  // Structured Response tab (Advanced modal). The list is server-rendered into
  // #structured-responses-container and rewritten through hxGet so CRUD and
  // ordering have one source of truth; field edits PATCH in place to avoid
  // collapsing the row the user is editing.
  var DEFAULT_SCHEMA =
    '{\n  "type": "object",\n  "properties": {\n    "text": {\n      "type": "string"\n    }\n  },\n  "required": ["text"],\n  "additionalProperties": false\n}';
  var DEFAULT_TEMPLATE = '{{{text}}}';

  function currentPresetId() {
    return (window.StateManager && StateManager.get('preset_id')) || '';
  }

  function patchResponse(id, patch) {
    return fetch('/api/structured-responses/' + id, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    }).then(function (r) {
      if (!r.ok) {
        return r.json().then(function (e) {
          if (window.showErrorToast) showErrorToast((e && e.detail) || 'Failed to save response');
          throw e;
        });
      }
      return r.json();
    });
  }

  window.reloadStructuredResponses = function () {
    var container = document.getElementById('structured-responses-container');
    if (!container) return Promise.resolve();
    var pid = currentPresetId();
    var url =
      '/partials/structured-responses' + (pid ? '?preset_id=' + encodeURIComponent(pid) : '');
    return hxGet(url, { target: '#structured-responses-container', swap: 'innerHTML' }).then(
      function () {
        setTimeout(window.initStructuredSortables, 30);
      },
    );
  };

  window.initStructuredSortables = function () {
    document
      .querySelectorAll('#structured-responses-container .structured-sortable')
      .forEach(function (list) {
        if (list._sortable) list._sortable.destroy();
        list._sortable = new Sortable(list, {
          animation: 150,
          ghostClass: 'sortable-ghost',
          handle: '.structured-handle',
          group: {
            name:
              'structured-' + (list.dataset.scope || '') + '-' + (list.dataset.scopeId || ''),
            pull: false,
            put: false,
          },
          onEnd: function () {
            window.updateStructuredPositions();
          },
        });
      });
  };

  window.updateStructuredPositions = function () {
    var ids = [];
    document
      .querySelectorAll('#structured-responses-container .structured-sortable .structured-item')
      .forEach(function (item) {
        ids.push(item.dataset.id);
      });
    fetch('/api/structured-responses/reorder', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids: ids }),
    });
  };

  window.handleStructuredUpdate = function (el, patch) {
    var item = el.closest('.structured-item');
    if (!item) return;
    patchResponse(item.dataset.id, patch).catch(function () {});
  };

  window.handleStructuredActive = function (el) {
    var item = el.closest('.structured-item');
    if (!item) return;
    var enabled = !el.classList.contains('active');
    // Activating is mutually exclusive per scope, so reload to reflect which
    // sibling got demoted.
    patchResponse(item.dataset.id, { enabled: enabled })
      .then(function () {
        return window.reloadStructuredResponses();
      })
      .catch(function () {});
  };

  window.toggleStructuredBody = function (el) {
    var item = el.closest('.structured-item');
    if (!item) return;
    var body = item.querySelector('.structured-body');
    var expanded = body.style.display !== 'none';
    body.style.display = expanded ? 'none' : 'block';
    item.classList.toggle('expanded', !expanded);
    el.setAttribute('aria-expanded', String(!expanded));
  };

  window.createStructuredResponse = function (scope, scopeId) {
    fetch('/api/structured-responses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        scope: scope,
        scope_id: scopeId || null,
        name: 'New response',
        json_schema: DEFAULT_SCHEMA,
        template: DEFAULT_TEMPLATE,
        enabled: true,
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
        return window.reloadStructuredResponses().then(function () {
          var list = document.querySelector(
            '#structured-responses-container .structured-sortable[data-scope="' + scope + '"]',
          );
          if (!list) return;
          var items = list.querySelectorAll('.structured-item');
          var created = items[items.length - 1];
          if (created) {
            var title = created.querySelector('.arranger-title-group');
            if (title) title.click();
          }
        });
      })
      .catch(function (e) {
        if (window.showErrorToast)
          showErrorToast((e && e.detail) || 'Could not create response');
      });
  };

  window.deleteStructuredResponse = function (el) {
    var item = el.closest('.structured-item');
    if (!item) return;
    fetch('/api/structured-responses/' + item.dataset.id, { method: 'DELETE' }).then(function () {
      window.reloadStructuredResponses();
    });
  };

  window.previewStructuredResponse = function (el) {
    var item = el.closest('.structured-item');
    if (!item) return;
    var out = item.querySelector('.structured-preview-out');
    var sample = item.querySelector('.structured-sample').value || '{"text": "Hello world!"}';
    fetch('/api/structured-responses/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        template: item.querySelector('.structured-template').value,
        json_sample: sample,
      }),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok) {
          out.textContent = (res.data && res.data.detail) || 'Preview failed';
          out.classList.add('structured-preview-error');
        } else {
          out.textContent = res.data.result;
          out.classList.remove('structured-preview-error');
        }
      });
  };
})();
