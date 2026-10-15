(function () {
  // Client-side single source of truth for character records.
  //
  // Seeded once from the server render, then kept authoritative by character
  // mutations (the card editor's upsert is the live path). The characters page
  // selector reads the list from here instead of a page-load snapshot, so a
  // rename updates the label without a reload.

  var _characters = [];
  var _listeners = [];

  function _emit(detail) {
    _listeners.slice().forEach(function (fn) { fn(detail); });
    if (window.dispatchEvent) {
      window.dispatchEvent(new CustomEvent('characters-changed', { detail: detail }));
    }
  }

  window.CharacterStore = {
    init: function (list) {
      _characters = Array.isArray(list) ? list : [];
      return _characters;
    },

    all: function () {
      return _characters;
    },

    get: function (id) {
      if (!id) return null;
      for (var i = 0; i < _characters.length; i++) {
        if (_characters[i].id === id) return _characters[i];
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

    upsert: function (character) {
      if (!character || !character.id) return;
      for (var i = 0; i < _characters.length; i++) {
        if (_characters[i].id === character.id) {
          _characters[i] = character;
          _emit({ action: 'upsert', id: character.id });
          return;
        }
      }
      _characters.push(character);
      _emit({ action: 'upsert', id: character.id });
    },

    remove: function (id) {
      for (var i = 0; i < _characters.length; i++) {
        if (_characters[i].id === id) {
          _characters.splice(i, 1);
          _emit({ action: 'remove', id: id });
          return;
        }
      }
    },

    // Re-pull the authoritative list. Character update responses are not the
    // full list record, so this is how the store catches up after a mutation.
    refresh: function () {
      return fetch(window.api.charactersList)
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (list) {
          if (Array.isArray(list)) {
            _characters = list;
            _emit({ action: 'refresh' });
          }
          return _characters;
        });
    },
  };
})();
