function _saveListPref(key, value) {
  localStorage.setItem(key, value);
  fetch('/api/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: key, value: value }),
  });
}

function _loadListPref(key, fallback) {
  var val = localStorage.getItem(key);
  if (val) return val;
  // Could load from API, but for UI prefs localStorage fallback is fine
  return fallback;
}

var _afterSwapHandlers = {};

window.ListManager = {
  setup: function (cfg) {
    var filterState = { query: '', filter: 'all', group: '' };

    function eachCard(fn) {
      var grid = document.getElementById(cfg.gridId);
      if (!grid) return;
      grid.querySelectorAll('.card').forEach(fn);
    }

    function collectGroups() {
      var groups = [];
      eachCard(function (card) {
        var g = (card.getAttribute(cfg.dataGroupAttr) || '').trim();
        if (g && groups.indexOf(g) === -1) groups.push(g);
      });
      groups.sort(function (a, b) { return a.localeCompare(b); });
      return groups;
    }

    function applyFilters() {
      var q = filterState.query.toLowerCase();
      eachCard(function (card) {
        var name = (card.getAttribute(cfg.dataNameAttr) || '').toLowerCase();
        var fav = (card.getAttribute(cfg.dataFavoriteAttr) || '0') === '1';
        var group = (card.getAttribute(cfg.dataGroupAttr) || '').trim();
        var ok = name.indexOf(q) !== -1;
        if (ok && filterState.filter === 'favorites') ok = fav;
        else if (ok && filterState.filter === 'group' && filterState.group) ok = group === filterState.group;
        card.style.display = ok ? '' : 'none';
      });
    }

    window[cfg.filterFn] = function (query) {
      filterState.query = query || '';
      applyFilters();
    };

    window[cfg.setFilterFn] = function (mode, value) {
      filterState.filter = mode || 'all';
      filterState.group = mode === 'group' ? (value || '') : '';
      applyFilters();
    };

    window[cfg.toggleFavoriteFn] = function (el) {
      var card = el.closest('.card');
      if (!card) return;
      var id = cfg.cardPrefix ? card.id.replace(cfg.cardPrefix, '') : '';
      var next = (card.getAttribute(cfg.dataFavoriteAttr) || '0') !== '1';
      fetch(cfg.apiEndpoint + '/' + id, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_favorite: next }),
      }).then(function (r) {
        if (!r.ok) return;
        card.setAttribute(cfg.dataFavoriteAttr, next ? '1' : '0');
        card.querySelectorAll('.fav-star').forEach(function (s) {
          s.classList.toggle('favorite-active', next);
        });
        applyFilters();
      });
    };

    window[cfg.getGroupsFn] = function () {
      return collectGroups();
    };

    window[cfg.sortFn] = function (mode) {
      _saveListPref(cfg.sortStorageKey, mode);
      var grid = document.getElementById(cfg.gridId);
      if (!grid) return;
      var cards = Array.from(grid.querySelectorAll('.card'));
      cards.sort(function (a, b) {
        var aName = a.getAttribute(cfg.dataNameAttr) || '';
        var bName = b.getAttribute(cfg.dataNameAttr) || '';
        var aCreated = a.getAttribute(cfg.dataCreatedAttr) || '';
        var bCreated = b.getAttribute(cfg.dataCreatedAttr) || '';
        if (mode === 'az') return aName.localeCompare(bName);
        if (mode === 'za') return bName.localeCompare(aName);
        if (mode === 'oldest') return aCreated.localeCompare(bCreated);
        return bCreated.localeCompare(aCreated);
      });
      cards.forEach(function (card) {
        grid.appendChild(card);
      });
      var sel = document.getElementById(cfg.sortSelectId);
      if (sel) sel.value = mode;
    };

    window[cfg.applyCompactFn] = function (compact) {
      var grid = document.getElementById(cfg.gridId);
      if (!grid) return;
      var view = compact ? 'compact' : 'full';
      grid.dataset.view = view;
      grid.style.gridTemplateColumns = compact
        ? 'repeat(3, minmax(200px, 1fr))'
        : 'repeat(auto-fill, minmax(160px, 1fr))';
      grid.querySelectorAll('.card').forEach(function (card) {
        var fullEl = card.querySelector('.' + cfg.viewFullClass);
        var compactEl = card.querySelector('.' + cfg.viewCompactClass);
        if (compact) {
          fullEl.style.display = 'none';
          compactEl.style.display = 'block';
        } else {
          fullEl.style.display = 'flex';
          compactEl.style.display = 'none';
        }
      });
      _saveListPref(cfg.viewStorageKey, view);
    };

    window[cfg.toggleCompactFn] = function () {
      var grid = document.getElementById(cfg.gridId);
      if (!grid) return;
      var compact = grid.dataset.view !== 'compact';
      window[cfg.applyCompactFn](compact);
    };

    window[cfg.newItemFn] = function () {
      var html =
        '<div class="mb-4">' +
        '<label class="text-xs font-bold text-muted block mb-2 uppercase tracking-wider">' +
        cfg.newItemLabel +
        '</label>' +
        '<input type="text" id="' +
        cfg.newItemInputId +
        '" class="form-control" placeholder="Enter name..." required>' +
        '</div>';
      window.customConfirm(html, function () {
        var name = document.getElementById(cfg.newItemInputId).value.trim();
        if (!name) return;
        fetch(cfg.apiEndpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: name }),
        }).then(function (r) {
          if (r.ok) {
            r.json().then(function (data) {
              var id = data.id;
              if (!id) return;
              var currentId = StateManager.get(cfg.stateKey) || '';
              var gridEl = document.getElementById(cfg.gridId);
              var compactView = gridEl && gridEl.dataset.view === 'compact';
              var url = cfg.cardEndpoint + id
                + '?current_' + cfg.stateKey + '=' + encodeURIComponent(currentId)
                + '&compact_view=' + (compactView ? 'true' : 'false');
              htmx.ajax('GET', url, { target: '#' + cfg.gridId, swap: 'beforeend' })
                .then(function () {
                  var val = localStorage.getItem(cfg.sortStorageKey);
                  if (val && window[cfg.sortFn]) window[cfg.sortFn](val);
                });
            });
          } else {
            r.text().then(function (t) {
              window.showErrorToast('Create failed: ' + t);
            });
          }
        });
      });
      setTimeout(function () {
        var input = document.getElementById(cfg.newItemInputId);
        if (input) {
          input.focus();
          input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') document.getElementById('global-confirm-btn').click();
          });
        }
      }, 100);
    };

    // Re-apply the active filter after any HTMX swap
    // (new/import/restore/edit card re-renders).
    if (_afterSwapHandlers[cfg.gridId]) {
      document.removeEventListener('htmx:afterSwap', _afterSwapHandlers[cfg.gridId]);
    }
    var afterSwapHandler = function () {
      var grid = document.getElementById(cfg.gridId);
      if (!grid) return;
      applyFilters();
    };
    _afterSwapHandlers[cfg.gridId] = afterSwapHandler;
    document.addEventListener('htmx:afterSwap', afterSwapHandler);

    (function () {
      var view = _loadListPref(cfg.viewStorageKey);
      if (view === 'compact') {
        window[cfg.applyCompactFn](true);
      }
      var sortVal = _loadListPref(cfg.sortStorageKey);
      if (sortVal) {
        window[cfg.sortFn](sortVal);
      }
      applyFilters();
    })();
  },
};
