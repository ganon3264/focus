(function () {
  // Display/input preferences. Loaded synchronously in <head> so the reading
  // width and the clock mode are in force before the first paint.
  var DEFAULTS = {
    send_key: 'enter',
    clock: '24h',
    chat_width: 800,
    prune_messages: true,
  };

  var prefs = Object.assign({}, DEFAULTS, window.PREFS || {});
  var root = document.documentElement;

  function apply() {
    root.style.setProperty('--chat-content-width', 'min(100%, ' + prefs.chat_width + 'px)');
    root.dataset.clock = prefs.clock;
  }

  function announce(keys) {
    for (var i = 0; i < keys.length; i++) {
      window.dispatchEvent(new CustomEvent('prefs-changed', {
        detail: { key: keys[i], value: prefs[keys[i]], all: Object.assign({}, prefs) },
      }));
    }
  }

  function set(patch) {
    var previous = Object.assign({}, prefs);
    var keys = [];
    for (var key in patch) {
      if (!(key in DEFAULTS)) continue;
      prefs[key] = patch[key];
      keys.push(key);
    }
    apply();
    announce(keys);

    if (!window.hxJson || !window.api) return Promise.resolve(prefs);
    return window.hxJson(window.api.settingsPrefs, 'PUT', patch)
      .then(function (resp) {
        if (!resp.ok) throw new Error('Could not save preferences');
        return resp.json();
      })
      .then(function (saved) {
        if (saved && typeof saved === 'object') {
          prefs = Object.assign({}, DEFAULTS, saved);
          apply();
        }
        return prefs;
      })
      .catch(function () {
        prefs = previous;
        apply();
        announce(keys);
        if (window.showErrorToast) window.showErrorToast('Could not save preferences');
      });
  }

  window.Prefs = {
    get: function (key) { return prefs[key]; },
    all: function () { return Object.assign({}, prefs); },
    set: set,
  };

  // Chips, switches and the width slider all write through one verb.
  window.actionSetPref = function (el, e) {
    // A range fires input on every drag tick; only its change commits.
    if (e && e.type === 'input') return;
    var key = el.dataset.pref;
    if (!key) return;
    var current = prefs[key];
    var value = el.dataset.value !== undefined ? el.dataset.value : el.value;

    if (el.dataset.toggle !== undefined) value = !current;
    else if (typeof current === 'boolean') value = value === 'true';
    else if (typeof current === 'number') value = Number(value);

    var patch = {};
    patch[key] = value;
    set(patch);

    var row = el.closest('.row');
    if (el.classList.contains('chip')) {
      var chips = row ? row.querySelectorAll('.chip') : [];
      for (var i = 0; i < chips.length; i++) chips[i].classList.toggle('active', chips[i] === el);
    } else if (el.classList.contains('switch')) {
      el.classList.toggle('active', value === true);
    }
    var readout = row ? row.querySelector('[data-pref-readout]') : null;
    if (readout) readout.textContent = value + 'px';
  };

  apply();
})();
