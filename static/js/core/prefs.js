(function () {
  // Display/input preferences. Loaded synchronously in <head> so the reading
  // width and the clock mode are in force before the first paint.
  var prefs = Object.assign({}, window.PREFS || {});
  var root = document.documentElement;

  function apply() {
    if (typeof prefs.chat_width === 'number') {
      root.style.setProperty('--chat-content-width', 'min(100%, ' + prefs.chat_width + 'px)');
    }
    if (prefs.clock) root.dataset.clock = prefs.clock;
  }

  function announce(keys) {
    for (var i = 0; i < keys.length; i++) {
      window.dispatchEvent(new CustomEvent('prefs-changed', {
        detail: { key: keys[i], value: prefs[keys[i]], all: Object.assign({}, prefs) },
      }));
    }
  }

  function adopt(saved, keys) {
    if (saved && typeof saved === 'object') prefs = saved;
    apply();
    announce(keys);
  }

  function failed(previous, keys) {
    prefs = previous;
    apply();
    announce(keys);
    if (window.showErrorToast) window.showErrorToast('Could not save preferences');
  }

  function set(patch) {
    var previous = prefs;
    var keys = Object.keys(patch);
    prefs = Object.assign({}, prefs, patch);
    apply();
    return window.hxJson(window.api.settingsPrefs, 'PUT', patch)
      .then(function (resp) {
        if (!resp.ok) throw new Error('save failed');
        return resp.json();
      })
      .then(function (saved) {
        adopt(saved, keys);
        return prefs;
      })
      .catch(function () {
        failed(previous, keys);
      });
  }

  // Drops the stored blob, so the server answers with its own defaults — the
  // one definition of "default" and the reason this needs no key list.
  function reset() {
    var previous = prefs;
    var keys = Object.keys(prefs);
    return window.hxJson(window.api.settingsPrefs, 'DELETE')
      .then(function (resp) {
        if (!resp.ok) throw new Error('reset failed');
        return resp.json();
      })
      .then(function (saved) {
        adopt(saved, keys);
        return prefs;
      })
      .catch(function () {
        failed(previous, keys);
      });
  }

  // Every `[data-pref]` control in `root` takes its state from `prefs`, so a
  // new preference needs a row, not a branch here.
  function syncForm(root) {
    if (!root || !root.querySelectorAll) return;

    var controls = root.querySelectorAll('[data-pref]');
    for (var i = 0; i < controls.length; i++) {
      var el = controls[i];
      var value = prefs[el.dataset.pref];
      if (el.classList.contains('chip')) {
        el.classList.toggle('active', el.dataset.value === String(value));
      } else if (el.classList.contains('switch')) {
        el.classList.toggle('active', value === true);
      } else if (el.value !== undefined) {
        el.value = value;
      }
    }

    var readouts = root.querySelectorAll('[data-pref-readout]');
    for (var j = 0; j < readouts.length; j++) {
      var readout = readouts[j];
      var current = prefs[readout.dataset.prefReadout];
      readout.textContent = current === undefined ? '' : current + (readout.dataset.prefUnit || '');
    }
  }

  window.Prefs = {
    get: function (key) { return prefs[key]; },
    all: function () { return Object.assign({}, prefs); },
    set: set,
    reset: reset,
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

    var row = el.closest('.row');
    var patch = {};
    patch[key] = value;
    var pending = set(patch);
    syncForm(row);
    pending.then(function () { syncForm(row); });
  };

  window.actionResetPrefs = function () {
    var body = document.getElementById('prefs-body');
    window.openConfirmModal('Restore every display preference to its default?', function () {
      window.Prefs.reset().then(function () { syncForm(body); });
    });
  };

  apply();
})();
