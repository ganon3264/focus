(function () {
  // Modal lifecycle controller — single owner of open/close/stack/ESC/dirty.
  // Dirty tracking is opt-in per modal via data attributes on the overlay:
  //   data-dirty-fields="sel1, sel2"   fields to compare (snapshot on open)
  //   data-dirty-label="this message"  or "#selector" resolved at confirm time
  // UI elements inside the overlay:
  //   [data-dirty-hint]  toggles .hidden
  //   [data-dirty-save]  toggles .disabled + .opacity-50
  // State changes dispatch `dirty-changed` CustomEvent on window: {id, dirty}.

  var stack = [];
  var registry = {};
  var dirtyStates = {};
  var openHooks = {};

  function overlay(id) {
    return document.getElementById(id);
  }

  function ensureRegistered(id, ov) {
    var cfg = registry[id];
    if (cfg && cfg.ov === ov) return;
    // Overlays can be recreated by htmx swaps (e.g. providers modal body),
    // so always re-attach to the current node.
    var fieldsAttr = (ov.getAttribute('data-dirty-fields') || '').trim();
    cfg = {
      ov: ov,
      fields: fieldsAttr
        ? fieldsAttr.split(',').map(function (s) { return s.trim(); }).filter(Boolean)
        : [],
      label: ov.getAttribute('data-dirty-label') || null,
    };
    registry[id] = cfg;
    if (cfg.fields.length) {
      ov.addEventListener('input', function () { ModalController.refresh(id); });
      ov.addEventListener('change', function () { ModalController.refresh(id); });
    }
  }

  function fieldsOf(id) {
    var cfg = registry[id];
    if (!cfg || !cfg.fields.length) return [];
    var ov = overlay(id);
    if (!ov) return [];
    var out = [];
    var seen = {};
    cfg.fields.forEach(function (sel) {
      var nodes = ov.querySelectorAll(sel);
      for (var i = 0; i < nodes.length; i++) {
        var f = nodes[i];
        var key = f.id || f.name || ('f' + out.length);
        if (seen[key]) continue;
        seen[key] = true;
        out.push({ key: key, el: f });
      }
    });
    return out;
  }

  function setDirtyUI(id, d) {
    var ov = overlay(id);
    if (!ov) return;
    ov.querySelectorAll('[data-dirty-hint]').forEach(function (el) {
      el.classList.toggle('hidden', !d);
    });
    ov.querySelectorAll('[data-dirty-save]').forEach(function (el) {
      el.disabled = !d;
      el.classList.toggle('opacity-50', !d);
    });
  }

  function emitDirty(id, d) {
    if (window.dispatchEvent) {
      window.dispatchEvent(new CustomEvent('dirty-changed', { detail: { id: id, dirty: d } }));
    }
  }

  function applyState(id, d) {
    setDirtyUI(id, d);
    emitDirty(id, d);
  }

  function capture(id) {
    var snap = {};
    fieldsOf(id).forEach(function (f) { snap[f.key] = f.el.value || ''; });
    dirtyStates[id] = { snapshot: snap, dirty: false };
    applyState(id, false);
  }

  function recompute(id) {
    var st = dirtyStates[id];
    if (!st) return;
    var d = false;
    fieldsOf(id).forEach(function (f) {
      var base = st.snapshot[f.key];
      if (base === undefined) {
        st.snapshot[f.key] = f.el.value || '';
        return;
      }
      if ((f.el.value || '') !== (base || '')) d = true;
    });
    if (st.dirty !== d) {
      st.dirty = d;
      applyState(id, d);
    }
  }

  function labelOf(id) {
    var cfg = registry[id];
    if (!cfg || !cfg.label) return null;
    var l = cfg.label;
    if (l.indexOf('#') === 0) {
      var ov = overlay(id);
      if (!ov) return null;
      var el = ov.querySelector(l);
      return el ? (el.value || el.textContent || '').trim() || null : null;
    }
    return l;
  }

  function forceClose(id) {
    var ov = overlay(id);
    if (ov) ov.classList.add('hidden');
    var idx = stack.indexOf(id);
    if (idx >= 0) stack.splice(idx, 1);
    delete dirtyStates[id];
  }

  var ModalController = {
    open: function (id) {
      var ov = overlay(id);
      if (!ov) return;
      ensureRegistered(id, ov);
      var wasHidden = ov.classList.contains('hidden');
      ov.classList.remove('hidden');
      var idx = stack.indexOf(id);
      if (idx >= 0) stack.splice(idx, 1);
      stack.push(id);
      if (wasHidden && openHooks[id]) {
        openHooks[id].forEach(function (fn) { fn(id); });
      }
      if (wasHidden || !dirtyStates[id]) capture(id);
    },

    close: function (id, opts) {
      opts = opts || {};
      if (!opts.discard && ModalController.isDirty(id)) {
        var label = labelOf(id);
        window.openConfirmModal(
          'Discard unsaved changes' + (label ? ' to "' + label + '"' : '') + '?',
          function () { forceClose(id); },
        );
        return;
      }
      forceClose(id);
    },

    closeTop: function () {
      if (!stack.length) return;
      ModalController.close(stack[stack.length - 1]);
    },

    isOpen: function (id) {
      return stack.indexOf(id) !== -1;
    },

    isDirty: function (id) {
      var st = dirtyStates[id];
      return !!(st && st.dirty);
    },

    setDirty: function (id, val) {
      var st = dirtyStates[id];
      if (!st) return;
      st.dirty = !!val;
      applyState(id, !!val);
    },

    refresh: function (id) {
      recompute(id);
    },

    onOpen: function (id, fn) {
      (openHooks[id] = openHooks[id] || []).push(fn);
    },
  };

  window.ModalController = ModalController;

  window.openModal = function (id) {
    ModalController.open(id);
  };

  window.closeModal = function (id, opts) {
    ModalController.close(id, opts);
  };

  // ESC: confirm modal first (acts as Cancel), then topmost modal, then lightbox.
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' && e.keyCode !== 27) return;
    var confirmEl = document.getElementById('global-confirm-modal');
    if (confirmEl && !confirmEl.classList.contains('hidden')) {
      if (window.closeConfirmModal) window.closeConfirmModal();
      return;
    }
    if (stack.length) {
      ModalController.closeTop();
      return;
    }
    var lb = document.getElementById('lightbox');
    if (lb && !lb.classList.contains('hidden') && window.closeLightbox) window.closeLightbox();
  });

  // Programmatic pickers (option picker, custom selects) don't fire input events.
  document.addEventListener('option-selected', recomputeOpen);
  document.addEventListener('custom-select:set', recomputeOpen);

  function recomputeOpen() {
    stack.slice().forEach(function (id) { recompute(id); });
  }

  // Register overlays present at load (overlays are static in the DOM).
  function registerStatic() {
    var ovs = document.querySelectorAll('.modal-overlay');
    for (var i = 0; i < ovs.length; i++) {
      ensureRegistered(ovs[i].id, ovs[i]);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', registerStatic);
  } else {
    registerStatic();
  }

  // Lazy content loads for list modals (preserved from the old openModal).
  function needsFetch(targetId) {
    var inner = document.querySelector(targetId);
    return !inner || !inner.children.length || inner.children[0].textContent === 'Loading…';
  }

  ModalController.onOpen('modal-characters', function () {
    if (needsFetch('#characters-modal-body-inner'))
      htmx.ajax('GET', window.api.partials.charactersModal + '?current_character_id=' + (StateManager.get('character_id') || ''), { target: '#characters-modal-body-inner', swap: 'innerHTML' });
  });

  ModalController.onOpen('modal-personas', function () {
    if (needsFetch('#personas-modal-body-inner'))
      htmx.ajax('GET', window.api.partials.personasModal + '?current_persona_id=' + (StateManager.get('persona_id') || ''), { target: '#personas-modal-body-inner', swap: 'innerHTML' });
  });

  ModalController.onOpen('modal-providers', function () {
    htmx.ajax('GET', window.api.partials.providersModal, { target: '#providers-modal-body-inner', swap: 'innerHTML' });
  });

  ModalController.onOpen('modal-backups', function () {
    if (window.BackupManager) BackupManager.loadList();
  });
})();
