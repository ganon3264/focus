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
  return {
    '--accent-hover': lightenHex(hex, 15),
    '--accent-dim': 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.15)',
    '--accent-faint': 'rgba(' + rgb.r + ',' + rgb.g + ',' + rgb.b + ',0.05)',
  };
}

// ── State ────────────────────────────────────────────────────────────────────
// window.THEMES / window.THEME_STATE are embedded server-side by the chat page.
// THEME_STATE: { dark_theme_id, light_theme_id, char_theme_id, char_name }

var THEMES = window.THEMES || [];
var THEME_STATE = window.THEME_STATE || {
  dark_theme_id: 'builtin-slate',
  light_theme_id: 'builtin-light',
  char_theme_id: null,
  char_name: null,
};

window.getTheme = function (id) {
  for (var i = 0; i < THEMES.length; i++) {
    if (THEMES[i].id === id) return THEMES[i];
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
  fetch('/api/settings/theme', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slot: slot, theme_id: themeId }),
  });
  _notify((slot === 'dark' ? 'Dark theme: ' : 'Light theme: ') + theme.name);
};

function _notify(message) {
  if (window.showInfoToast) window.showInfoToast(message);
}

// ── CRUD ─────────────────────────────────────────────────────────────────────

window.saveTheme = function (name, colors, id, done) {
  var url = '/api/themes' + (id ? '/' + id : '');
  var method = id ? 'PATCH' : 'POST';
  fetch(url, {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: name, colors: colors }),
  })
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
  fetch('/api/themes/' + id + '/reset', { method: 'POST' })
    .then(function (r) {
      if (done) done(r.ok);
    })
    .catch(function () {
      if (done) done(false);
    });
};

window.deleteTheme = function (id, done) {
  fetch('/api/themes/' + id, { method: 'DELETE' })
    .then(function (r) {
      if (done) done(r.ok);
    })
    .catch(function () {
      if (done) done(false);
    });
};

window.refreshThemes = function (cb) {
  fetch('/api/themes')
    .then(function (r) {
      return r.json();
    })
    .then(function (list) {
      THEMES = list || [];
      window.dispatchEvent(new CustomEvent('theme-state-changed'));
      if (cb) cb();
    })
    .catch(function () {
      if (cb) cb();
    });
};

// ── Picker preview (color inputs) ────────────────────────────────────────────

function previewThemeColor(input) {
  const varName = input.getAttribute('data-var');
  document.documentElement.style.setProperty(varName, input.value);
  if (varName === '--accent') {
    const derivatives = computeAccentDerivatives(input.value);
    for (const [key, val] of Object.entries(derivatives)) {
      document.documentElement.style.setProperty(key, val);
    }
  }
}

function resetThemePreview() {
  window.reapplyTheme();
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

    setSlot: function (slot, id) {
      window.setSlot(slot, id);
      this.refresh();
    },

    // Unsaved-changes detection: dirty = name or any picker color differs
    // from the selected theme's stored values. Live preview is NOT saved —
    // this is what tells the user otherwise.
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
      var inputs = this._readPickers();
      var self = this;
      this.dirty = Object.keys(inputs).some(function (k) {
        var v = (inputs[k] || '').toLowerCase();
        var s = (stored[k] || '').toLowerCase();
        return v !== s;
      });
    },

    switchTo: function (id) {
      if (id === this.selectedId) return;
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
      this.selectedIsSystem = !!t.is_system;
      this.editName = t.name;
      this.editColors = Object.assign({}, t.colors);
      this.dirty = false;
      this.loadPickers();
      return true;
    },

    create: function () {
      var name = this.editName.trim();
      if (!name) {
        _notify('Enter a theme name first');
        return;
      }
      var colors = this._readPickers();
      var self = this;
      window.saveTheme(name, colors, null, function (ok, id) {
        if (!ok) return;
        _notify('Theme "' + name + '" created');
        window.refreshThemes(function () {
          if (id) {
            self.select(id);
            if (id === window.effectiveThemeId()) window.reapplyTheme();
          }
        });
      });
    },

    loadPickers: function () {
      document.querySelectorAll('#theme-color-pickers input[type="color"]').forEach(function (input) {
        var varName = input.getAttribute('data-var');
        input.value = this.editColors[varName] || '#000000';
      }, this);
    },

    _readPickers: function () {
      var out = {};
      document.querySelectorAll('#theme-color-pickers input[type="color"]').forEach(function (input) {
        out[input.getAttribute('data-var')] = input.value;
      });
      return out;
    },

    save: function () {
      var name = this.editName.trim();
      if (!name) {
        _notify('Enter a theme name first');
        return;
      }
      var colors = this._readPickers();
      var self = this;
      window.saveTheme(name, colors, this.selectedId, function (ok) {
        if (!ok) return;
        self.dirty = false;
        _notify('Theme saved');
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
          _notify('Theme deleted');
          window.refreshThemes();
          window.reapplyTheme();
          self.refresh();
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
          _notify('Theme reset to default');
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
      fetch('/api/characters/' + id)
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
      fetch('/api/characters/' + id)
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
