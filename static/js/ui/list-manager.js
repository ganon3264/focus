// The sort mode lives in the settings table (the server renders it into
// data-sort-mode on the grid, so a reload restores the order with no browser
// copy to drift from it).
function saveListSort(key, value) {
  hxJson(api.settings, 'PATCH', { key: key, value: value });
}

function listSortMode(gridId, fallback) {
  var grid = document.getElementById(gridId);
  return (grid && grid.getAttribute('data-sort-mode')) || fallback || 'newest';
}

window.saveListSort = saveListSort;
window.listSortMode = listSortMode;

var _afterSwapHandlers = {};

window.ListManager = {
  setup: function (cfg) {
    var filterState = { query: '', filter: 'all', group: '' };

    function eachCard(fn) {
      var grid = document.getElementById(cfg.gridId);
      if (!grid) return;
      grid.querySelectorAll('[data-ui="entity-row"]').forEach(fn);
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
      var card = el.closest('[data-ui="entity-row"]');
      if (!card) return;
      var id = cfg.cardPrefix ? card.id.replace(cfg.cardPrefix, '') : '';
      var next = (card.getAttribute(cfg.dataFavoriteAttr) || '0') !== '1';
      hxJson(cfg.apiEndpoint + '/' + id, 'PATCH', { is_favorite: next }).then(function (r) {
        if (!r.ok) return;
        card.setAttribute(cfg.dataFavoriteAttr, next ? '1' : '0');
        card.querySelectorAll('[data-ui="fav-star"]').forEach(function (s) {
          s.classList.toggle('favorite-active', next);
        });
        applyFilters();
      });
    };

    window[cfg.getGroupsFn] = function () {
      return collectGroups();
    };

    window[cfg.sortFn] = function (mode) {
      var grid = document.getElementById(cfg.gridId);
      if (!grid) return;
      grid.setAttribute('data-sort-mode', mode);
      var cards = Array.from(grid.querySelectorAll('[data-ui="entity-row"]'));
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

    window[cfg.newItemFn] = function () {
      var html =
        '<div class="form-group">' +
        '<label>' +
        cfg.newItemLabel +
        '</label>' +
        '<input type="text" id="' +
        cfg.newItemInputId +
        '" class="field" placeholder="Enter name..." required>' +
        '</div>';
      window.customConfirm(html, function () {
        var name = document.getElementById(cfg.newItemInputId).value.trim();
        if (!name) return;
        hxJson(cfg.apiEndpoint, 'POST', { name: name }).then(function (r) {
          if (r.ok) {
            r.json().then(function (data) {
              var id = data.id;
              if (!id) return;
              var currentId = StateManager.get(cfg.stateKey) || '';
              var url = cfg.cardEndpoint + id
                + '?current_' + cfg.stateKey + '=' + encodeURIComponent(currentId);
              hxGet(url, { target: '#' + cfg.gridId, swap: 'beforeend' })
                .then(function () {
                  if (window[cfg.sortFn]) window[cfg.sortFn](listSortMode(cfg.gridId));
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
      window[cfg.sortFn](listSortMode(cfg.gridId));
      applyFilters();
    })();
  },
};
