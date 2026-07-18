// Shared list management for character/persona modal grids.
// Call ListManager.setup({ filterFn: 'filterCharacters', sortFn: 'sortCharacters', ... })
// to create the expected-named global functions so existing onclick handlers keep working.

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

window.ListManager = {
  setup: function (cfg) {
    window[cfg.filterFn] = function (query) {
      var q = (query || '').toLowerCase();
      document.querySelectorAll('#' + cfg.gridId + ' .card').forEach(function (card) {
        var name = card.getAttribute(cfg.dataNameAttr) || '';
        card.style.display = name.indexOf(q) !== -1 ? '' : 'none';
      });
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
      document.getElementById(cfg.sortSelectId).value = mode;
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
          if (r.ok) htmx.ajax('GET', cfg.hxRoute, { target: cfg.hxTarget, swap: 'innerHTML' });
          else
            r.text().then(function (t) {
              alert('Create failed: ' + t);
            });
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

    // Restore saved view/sort state
    (function () {
      var view = _loadListPref(cfg.viewStorageKey);
      if (view === 'compact') {
        window[cfg.applyCompactFn](true);
      }
      var sortVal = _loadListPref(cfg.sortStorageKey);
      if (sortVal) {
        window[cfg.sortFn](sortVal);
      }
    })();
  },
};
