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
      },

      capture: function () {
        var snap = {};
        this._fields().forEach(function (f) { snap[f.key] = f.el.value || ''; });
        this._snapshot = snap;
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

  window.markDirtyModal = function (id) {
    var chk = checks[id];
    if (chk && chk._self) chk._self.dirty = true;
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
