function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? { r: parseInt(result[1], 16), g: parseInt(result[2], 16), b: parseInt(result[3], 16) }
    : null;
}

function lightenHex(hex, percent) {
  const rgb = hexToRgb(hex);
  if (!rgb) return hex;
  const f = percent / 100;
  const l = (c) => Math.round(c + (255 - c) * f);
  return '#' + [l(rgb.r), l(rgb.g), l(rgb.b)].map((c) => c.toString(16).padStart(2, '0')).join('');
}

function computeAccentDerivatives(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return {};
  var luma = 0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b;
  return {
    '--accent-hover': lightenHex(hex, 15),
    '--accent-dim': 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.15)',
    '--accent-faint': 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.05)',
    '--text-on-accent': luma > 145 ? '#16181c' : '#ffffff',
  };
}

// ── State ────────────────────────────────────────────────────────────────────
// window.THEMES / window.THEME_STATE are embedded server-side by the chat page.
// THEME_STATE: { dark_theme_id, light_theme_id, char_theme_id, char_name }

var THEME_STATE = window.THEME_STATE || {
  dark_theme_id: 'builtin-slate',
  light_theme_id: 'builtin-light',
  char_theme_id: null,
  char_name: null,
};

window.getTheme = function (id) {
  var themes = window.THEMES || [];
  for (var i = 0; i < themes.length; i++) {
    if (themes[i].id === id) return themes[i];
  }
  return null;
};

function systemDark() {
  if (!window.matchMedia) return true;
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function effectiveThemeId() {
  if (THEME_STATE.char_theme_id) return THEME_STATE.char_theme_id;
  return systemDark() ? THEME_STATE.dark_theme_id : THEME_STATE.light_theme_id;
}

window.effectiveThemeId = effectiveThemeId;

function resolvePalette(theme) {
  var palette = {};
  for (var key in theme.colors || {}) palette[key] = theme.colors[key];
  if (palette['--accent']) {
    var derivatives = computeAccentDerivatives(palette['--accent']);
    for (var d in derivatives) palette[d] = derivatives[d];
  }
  return palette;
}

function applyPalette(palette) {
  for (var key in palette) {
    document.documentElement.style.setProperty(key, palette[key]);
  }
}

function _cacheState() {
  try {
    var dark = window.getTheme(THEME_STATE.dark_theme_id) || window.getTheme('builtin-slate');
    var light = window.getTheme(THEME_STATE.light_theme_id) || window.getTheme('builtin-light');
    localStorage.setItem(
      'focus-theme-state',
      JSON.stringify({
        darkId: dark.id,
        darkColors: dark.colors,
        lightId: light.id,
        lightColors: light.colors,
      }),
    );
    localStorage.removeItem('focus-custom-theme');
  } catch (e) {}
}

function _applyEffective() {
  var theme = window.getTheme(effectiveThemeId()) || window.getTheme('builtin-slate');
  if (!theme) return;
  applyPalette(resolvePalette(theme));
  _cacheState();
  window.dispatchEvent(new CustomEvent('theme-state-changed'));
}

window.reapplyTheme = _applyEffective;

window.setSlot = function (slot, themeId) {
  if (slot !== 'dark' && slot !== 'light') return;
  var theme = window.getTheme(themeId);
  if (!theme) return;
  if (slot === 'dark') THEME_STATE.dark_theme_id = themeId;
  else THEME_STATE.light_theme_id = themeId;
  _applyEffective();
  hxJson(api.settingsTheme, 'PUT', { slot: slot, theme_id: themeId });
  window.showToast((slot === 'dark' ? 'Dark theme: ' : 'Light theme: ') + theme.name);
};

// ── CRUD ─────────────────────────────────────────────────────────────────────

window.saveTheme = function (name, colors, id, done) {
  var url = id ? api.theme(id) : api.themes;
  var method = id ? 'PATCH' : 'POST';
  hxJson(url, method, { name: name, colors: colors })
    .then(function (r) {
      return r.json().then(function (data) {
        if (done) done(r.ok, r.ok && data.id ? data.id : null);
      });
    })
    .catch(function () {
      if (done) done(false);
    });
};

window.resetTheme = function (id, done) {
  hxJson(api.themeReset(id), 'POST')
    .then(function (r) {
      if (done) done(r.ok);
    })
    .catch(function () {
      if (done) done(false);
    });
};

window.deleteTheme = function (id, done) {
  hxJson(api.theme(id), 'DELETE')
    .then(function (r) {
      if (done) done(r.ok);
    })
    .catch(function () {
      if (done) done(false);
    });
};

window.refreshThemes = function (cb) {
  hxFetch(api.themes)
    .then(function (r) {
      return r.json();
    })
    .then(function (list) {
      window.THEMES = list || [];
      window.dispatchEvent(new CustomEvent('theme-state-changed'));
      if (cb) cb();
    })
    .catch(function () {
      if (cb) cb();
    });
};

// ── Picker preview (color inputs) ────────────────────────────────────────────

function previewThemeColor(varName, value) {
  document.documentElement.style.setProperty(varName, value);
  if (varName === '--accent') {
    const derivatives = computeAccentDerivatives(value);
    for (const [key, val] of Object.entries(derivatives)) {
      document.documentElement.style.setProperty(key, val);
    }
  }
}

function resetThemePreview() {
  window.reapplyTheme();
}

// ── Creating a theme ─────────────────────────────────────────────────────────
// A copy has to carry a name no other theme holds; a typed name is the user's
// call. The create POST, the toast and the "select it" follow-up live in one
// place because the copy verb and the New dialog both start a theme.
function uniqueThemeName(base) {
  var taken = (window.THEMES || []).map(function (t) {
    return (t.name || '').toLowerCase();
  });
  if (taken.indexOf(base.toLowerCase()) === -1) return base;
  var n = 2;
  while (taken.indexOf((base + ' ' + n).toLowerCase()) !== -1) n += 1;
  return base + ' ' + n;
}

// "Paper Copy" copied again is "Paper Copy 2", not "Paper Copy Copy": a copy
// of a copy keeps numbering the same stem.
function copyThemeName(name) {
  var stem = name.replace(/ copy( \d+)?$/i, '');
  return uniqueThemeName(stem + ' Copy');
}

window.createTheme = function (name, colors, done) {
  window.saveTheme(name, colors, null, function (ok, id) {
    if (!ok) {
      window.showToast('Could not create the theme', { type: 'error' });
      return;
    }
    window.showToast('Theme "' + name + '" created', { type: 'success' });
    window.refreshThemes(function () {
      if (id) window.dispatchEvent(new CustomEvent('theme-created', { detail: id }));
      if (done) done(true, id);
    });
  });
};

window.openThemeNewModal = function () {
  var input = document.getElementById('theme-new-name');
  var form = document.getElementById('theme-new-form');
  if (!input || !form) return;
  form.querySelectorAll('[data-theme-base-name]').forEach(function (el) {
    var slot = el.getAttribute('data-theme-base-name');
    var theme = window.getTheme(
      slot === 'light' ? window.THEME_STATE.light_theme_id : window.THEME_STATE.dark_theme_id,
    );
    el.textContent = theme ? theme.name : '—';
  });
  input.value = '';
  openModal('modal-theme-new');
  setTimeout(function () {
    input.focus();
    input.select();
  }, 0);
};

window.actionSubmitThemeNew = function (form, e) {
  e.preventDefault();
  var input = document.getElementById('theme-new-name');
  var name = (input && input.value ? input.value : '').trim();
  if (!name) {
    window.showToast('Enter a theme name first', { type: 'error', duration: 4000 });
    if (input) input.focus();
    return;
  }
  var picked = form.querySelector('input[name="theme-base"]:checked');
  var baseId =
    picked && picked.value === 'light' ? window.THEME_STATE.light_theme_id : window.THEME_STATE.dark_theme_id;
  var base = window.getTheme(baseId);
  window.createTheme(name, base ? Object.assign({}, base.colors) : {}, function (ok) {
    if (ok) window.closeModal('modal-theme-new');
  });
};

// The editor opens under its own row, so a row near the bottom of a long list
// would otherwise open its palette out of view.
function revealSelectedTheme() {
  var next = window.Alpine ? window.Alpine.nextTick : function (fn) { setTimeout(fn, 0); };
  next(function () {
    var item = document.querySelector('#modal-themes .theme-item.open');
    if (item && item.scrollIntoView) item.scrollIntoView({ block: 'start' });
  });
}

// ── Theme modal (Alpine) ─────────────────────────────────────────────────────
// Click a theme to select it for editing; Dark/Light buttons assign the
// global dark/light slots. Save updates in place; New starts a fresh draft.

window.themeModalState = function () {
  return {
    themes: [],
    darkId: '',
    lightId: '',
    charThemeId: null,
    charName: null,
    selectedId: null,
    openId: null,
    selectedIsSystem: false,
    editName: '',
    editColors: {},
    dirty: false,

    init: function () {
      this.refresh();
      this.select(window.effectiveThemeId());
    },

    refresh: function () {
      this.themes = (window.THEMES || []).slice();
      this.darkId = window.THEME_STATE.dark_theme_id || '';
      this.lightId = window.THEME_STATE.light_theme_id || '';
      this.charThemeId = window.THEME_STATE.char_theme_id || null;
      this.charName = window.THEME_STATE.char_name || null;
    },

    // A created theme only takes the editor when there is nothing to lose: a
    // dirty draft would otherwise be thrown away by an action that never asked
    // to switch themes.
    onThemeCreated: function (id) {
      if (this.dirty) {
        this.refresh();
        return;
      }
      this.select(id);
    },

    setSlot: function (slot, id) {
      window.setSlot(slot, id);
      this.refresh();
    },

    // The draft is the editor's single source: the pickers bind to editColors
    // and paint :root through the same call, so what is previewed, what is
    // saved and what Save thinks is dirty can never drift apart.
    setColor: function (varName, value) {
      this.editColors[varName] = value;
      previewThemeColor(varName, value);
      this.markDirty();
    },

    markDirty: function () {
      var t = this.selectedId ? window.getTheme(this.selectedId) : null;
      if (!t) {
        this.dirty = true;
        return;
      }
      if (this.editName.trim() !== t.name) {
        this.dirty = true;
        return;
      }
      var stored = t.colors || {};
      var colors = this.editColors;
      this.dirty = Object.keys(colors).some(function (k) {
        return (colors[k] || '').toLowerCase() !== (stored[k] || '').toLowerCase();
      });
    },

    switchTo: function (id) {
      // The selected row folds and unfolds on its own; its draft survives.
      if (id === this.selectedId) {
        this.openId = this.openId === id ? null : id;
        if (this.openId) revealSelectedTheme();
        return;
      }
      if (this.dirty) {
        var self = this;
        window.openConfirmModal(
          'Discard unsaved changes to "' + this.editName + '"?',
          function () {
            self.select(id);
          },
        );
        return;
      }
      this.select(id);
    },

    select: function (id) {
      var t = window.getTheme(id);
      if (!t) return false;
      this.selectedId = t.id;
      this.openId = t.id;
      this.selectedIsSystem = !!t.is_system;
      this.editName = t.name;
      this.editColors = Object.assign({}, t.colors);
      this.dirty = false;
      window.reapplyTheme();
      revealSelectedTheme();
      return true;
    },

    duplicate: function (id) {
      var t = window.getTheme(id);
      if (!t) return;
      var name = copyThemeName(t.name);
      window.createTheme(name, Object.assign({}, t.colors));
    },

    save: function () {
      var name = this.editName.trim();
      if (!name) {
        window.showToast('Enter a theme name first', { type: 'error', duration: 4000 });
        return;
      }
      // The draft keeps the tokens the board does not expose (e.g. --text-faint)
      // as they were copied on select, so editing a built-in does not strip it
      // back to the derived fallback.
      var colors = Object.assign({}, this.editColors);
      var self = this;
      window.saveTheme(name, colors, this.selectedId, function (ok) {
        if (!ok) return;
        self.dirty = false;
        window.showToast('Theme saved', { type: 'success' });
        window.refreshThemes(function () {
          if (self.selectedId === window.effectiveThemeId()) window.reapplyTheme();
        });
        window.closeModal('modal-themes');
      });
    },

    remove: function (id, name) {
      var self = this;
      window.openConfirmModal('Delete theme "' + name + '"?', function () {
        window.deleteTheme(id, function (ok) {
          if (!ok) return;
          window.showToast('Theme deleted', { type: 'success' });
          window.reapplyTheme();
          window.refreshThemes(function () {
            if (self.selectedId === id) {
              var next = window.effectiveThemeId();
              if (!self.select(next)) self.select((window.THEMES[0] || {}).id);
            }
            self.refresh();
          });
        });
      });
    },

    reset: function () {
      if (!this.selectedId || !this.selectedIsSystem) return;
      var id = this.selectedId;
      var self = this;
      window.openConfirmModal('Reset "' + this.editName + '" to its default look?', function () {
        window.resetTheme(id, function (ok) {
          if (!ok) return;
          window.showToast('Theme reset to default', { type: 'success' });
          window.refreshThemes(function () {
            self.select(id);
            if (id === window.effectiveThemeId()) window.reapplyTheme();
          });
        });
      });
    },
  };
};

// ── Character theme picker (character edit modal) ────────────────────────────

window.openCharThemePicker = function () {
  var opts = [{ value: '', label: 'Inherit (global)' }];
  (window.THEMES || []).forEach(function (t) {
    opts.push({ value: t.id, label: t.name });
  });
  window.openOptionPicker(opts, 'Select Theme', function (value, label) {
    var idInput = document.getElementById('edit-char-theme-id');
    var labelEl = document.getElementById('edit-char-theme-label');
    if (!idInput || !labelEl) return;
    idInput.value = value || '';
    labelEl.textContent = label;
    labelEl.classList.toggle('text-muted', !value);
  });
};

if (window.ModalController) window.ModalController.onOpen('modal-themes', revealSelectedTheme);

// ── Follow system scheme live ────────────────────────────────────────────────

(function () {
  var mq = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)');
  if (mq) {
    var handler = function () {
      window.reapplyTheme();
    };
    if (mq.addEventListener) mq.addEventListener('change', handler);
    else if (mq.addListener) mq.addListener(handler);
  }

  if (window.StateManager) {
    StateManager.on('character-changed', function () {
      var id = StateManager.get('character_id');
      if (!id) {
        window.THEME_STATE.char_theme_id = null;
        window.THEME_STATE.char_name = null;
        window.reapplyTheme();
        return;
      }
      hxFetch(api.characters(id))
        .then(function (r) {
          return r.json();
        })
        .then(function (c) {
          window.THEME_STATE.char_theme_id = c && c.theme_id ? c.theme_id : null;
          window.THEME_STATE.char_name = c && c.name ? c.name : null;
          window.reapplyTheme();
        })
        .catch(function () {});
    });

    document.addEventListener('character-edited', function (e) {
      var id = e.detail && e.detail.id;
      if (!id || id !== StateManager.get('character_id')) return;
      hxFetch(api.characters(id))
        .then(function (r) {
          return r.json();
        })
        .then(function (c) {
          window.THEME_STATE.char_theme_id = c && c.theme_id ? c.theme_id : null;
          window.THEME_STATE.char_name = c && c.name ? c.name : null;
          window.reapplyTheme();
        })
        .catch(function () {});
    });
  }

  // Apply the server-embedded state on load (overrides any stale cache).
  _applyEffective();
})();
