(function () {
  if (window.__dirtyStateLoaded) return;
  window.__dirtyStateLoaded = true;

  var checks = (window._dirtyChecks = window._dirtyChecks || {});

  function modalIdOf(el) {
    var m = el && el.closest ? el.closest('.modal-overlay') : null;
    return m ? m.id : null;
  }

  window.dirtyModalState = function (cfg) {
    cfg = cfg || {};
    var self = null;
    var state = {
      dirty: false,
      _snapshot: {},
      _seeded: {},
      _observer: null,

      init: function () {
        self = this;
        var id = modalIdOf(this.$el);
        if (id) {
          checks[id] = {
            _self: this,
            isDirty: function () { return self.dirty; },
            label: function () { return self._label(); },
            capture: function () { self.capture(); },
            refresh: function () { self.markDirty(); },
          };
        }
        this.capture();
        this._watch();
      },

      destroy: function () {
        if (this._observer) this._observer.disconnect();
        var id = modalIdOf(this.$el);
        if (id && checks[id] && checks[id]._self === this) {
          delete checks[id];
        }
      },

      capture: function () {
        var snap = {};
        this._fields().forEach(function (f) { snap[f.key] = f.el.value || ''; });
        this._snapshot = snap;
        this._seeded = {};
        this.dirty = false;
      },

      markDirty: function () {
        var snap = this._snapshot;
        var d = false;
        this._fields().forEach(function (f) {
          var baseline = snap[f.key];
          if (baseline === undefined) {
            snap[f.key] = f.el.value || '';
            return;
          }
          if ((f.el.value || '') !== (baseline || '')) d = true;
        });
        this.dirty = d;
      },

      _watch: function () {
        var self = this;
        var sels = typeof cfg.fields === 'string' ? [cfg.fields] : (cfg.fields || []);
        var keep = cfg.keepBaseline || [];
        this._observer = new MutationObserver(function (mutations) {
          var touched = false;
          mutations.forEach(function (m) {
            if (!m.addedNodes) return;
            Array.prototype.forEach.call(m.addedNodes, function (n) {
              if (n.nodeType !== 1) return;
              var els = n.querySelectorAll ? n.querySelectorAll('input,textarea,select') : [];
              els = Array.prototype.slice.call(els);
              if (n.matches && n.matches('input,textarea,select')) els.push(n);
              els.forEach(function (el) {
                var key = el.id || el.name;
                if (!key) return;
                var tracked = sels.some(function (s) { return el.matches(s); });
                if (!tracked) return;
                if (keep.indexOf(key) !== -1 && self._seeded[key]) {
                  touched = true;
                  return;
                }
                self._snapshot[key] = el.value || '';
                self._seeded[key] = true;
                touched = true;
              });
            });
          });
          if (touched) self.markDirty();
        });
        this._observer.observe(this.$el, { childList: true, subtree: true });
      },

      _fields: function () {
        var sels = cfg.fields;
        if (typeof sels === 'string') sels = [sels];
        var out = [];
        (sels || []).forEach(function (s) {
          (this.querySelectorAll(s) || []).forEach(function (f) {
            out.push({ key: f.id || f.name || out.length, el: f });
          });
        }, this.$el);
        return out;
      },

      _label: function () {
        var l = cfg.label;
        if (!l) return null;
        if (typeof l === 'function') return l() || null;
        if (typeof l === 'string' && l.indexOf('#') === 0) {
          var el = this.$el.querySelector(l);
          return el ? (el.value || el.textContent || '').trim() || null : null;
        }
        return l || null;
      },
    };
    return state;
  };

  window.captureDirty = function (id) {
    var chk = checks[id];
    if (chk && chk.capture) chk.capture();
  };

  window.refreshDirty = function (id) {
    var chk = checks[id];
    if (chk && chk.refresh) chk.refresh();
  };

  function refreshVisible() {
    Object.keys(checks).forEach(function (id) {
      var el = document.getElementById(id);
      if (el && !el.classList.contains('hidden')) checks[id].refresh();
    });
  }

  document.addEventListener('option-selected', refreshVisible);
  document.addEventListener('custom-select:set', refreshVisible);
})();
