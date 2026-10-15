(function () {
  // Client-side single source of truth for provider records.
  //
  // Seeded once from the server render, then kept authoritative by every
  // provider mutation (create/edit/delete call refresh()). The status panel,
  // sampler and generation (Claude cache) read the active provider from here
  // instead of a page-load snapshot, so a provider created after load is
  // visible immediately.
  //
  // Selection stays in StateManager (provider_id/provider_type); this module
  // owns only the provider data.

  var _providers = [];
  var _listeners = [];

  function _emit(detail) {
    _listeners.slice().forEach(function (fn) { fn(detail); });
    if (window.dispatchEvent) {
      window.dispatchEvent(new CustomEvent('providers-changed', { detail: detail }));
    }
  }

  window.ProviderStore = {
    init: function (list) {
      _providers = Array.isArray(list) ? list : [];
      return _providers;
    },

    all: function () {
      return _providers;
    },

    get: function (id) {
      if (!id) return null;
      for (var i = 0; i < _providers.length; i++) {
        if (_providers[i].id === id) return _providers[i];
      }
      return null;
    },

    on: function (fn) {
      if (typeof fn === 'function') _listeners.push(fn);
    },

    off: function (fn) {
      var i = _listeners.indexOf(fn);
      if (i >= 0) _listeners.splice(i, 1);
    },

    upsert: function (provider) {
      if (!provider || !provider.id) return;
      for (var i = 0; i < _providers.length; i++) {
        if (_providers[i].id === provider.id) {
          _providers[i] = provider;
          _emit({ action: 'upsert', id: provider.id });
          return;
        }
      }
      _providers.push(provider);
      _emit({ action: 'upsert', id: provider.id });
    },

    remove: function (id) {
      for (var i = 0; i < _providers.length; i++) {
        if (_providers[i].id === id) {
          _providers.splice(i, 1);
          _emit({ action: 'remove', id: id });
          return;
        }
      }
    },

    // Re-pull the authoritative list. Provider create/update responses are not
    // the full record, so this is how the store catches up after a mutation.
    refresh: function () {
      return fetch(window.api.providers)
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (list) {
          if (Array.isArray(list)) {
            _providers = list;
            _emit({ action: 'refresh' });
          }
          return _providers;
        });
    },
  };
})();
