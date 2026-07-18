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

const PRESET_THEMES = {
  default: {
    '--bg': '#0b0d10',
    '--surface': '#13151a',
    '--surface-2': '#1c1f26',
    '--surface-3': '#2b303b',
    '--border': '#232730',
    '--accent': '#6366f1',
    '--text': '#f1f3f5',
    '--text-muted': '#8b949e',
    '--role-user': '#10b981',
    '--role-assistant': '#f59e0b',
  },
  midnight: {
    '--bg': '#000000',
    '--surface': '#090909',
    '--surface-2': '#111111',
    '--surface-3': '#1a1a1a',
    '--border': '#222222',
    '--accent': '#3b82f6',
    '--text': '#ffffff',
    '--text-muted': '#9ca3af',
    '--role-user': '#34d399',
    '--role-assistant': '#fbbf24',
  },
  light: {
    '--bg': '#f8fafc',
    '--surface': '#ffffff',
    '--surface-2': '#f1f5f9',
    '--surface-3': '#e2e8f0',
    '--border': '#e2e8f0',
    '--accent': '#4f46e5',
    '--text': '#0f172a',
    '--text-muted': '#64748b',
    '--role-user': '#059669',
    '--role-assistant': '#d97706',
  },
};

let _savedThemeBackup = {};

const _themeTrigger = document.querySelector('[onclick="openModal(\'modal-themes\')"]');
if (_themeTrigger) {
  _themeTrigger.addEventListener('click', function () {
    _savedThemeBackup = {};
    const rootStyle = getComputedStyle(document.documentElement);
    document.querySelectorAll('#theme-color-pickers input[type="color"]').forEach((input) => {
      const varName = input.getAttribute('data-var');
      let color = rootStyle.getPropertyValue(varName).trim();
      if (color.startsWith('rgba')) {
        color = '#000000';
      }
      if (color.length === 4) {
        color = '#' + color[1] + color[1] + color[2] + color[2] + color[3] + color[3];
      }
      input.value = color || '#000000';
      _savedThemeBackup[varName] = color;
    });
  });
}

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

function _saveThemeToApi(theme) {
  fetch('/api/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: 'theme_json', value: JSON.stringify(theme) }),
  });
}

function applyPresetTheme(presetName) {
  const base = PRESET_THEMES[presetName];
  if (!base) return;
  const theme = { ...base };
  const accent = theme['--accent'];
  if (accent) {
    Object.assign(theme, computeAccentDerivatives(accent));
  }
  localStorage.setItem('focus-custom-theme', JSON.stringify(theme));
  _saveThemeToApi(theme);
  for (const [key, value] of Object.entries(theme)) {
    document.documentElement.style.setProperty(key, value);
    const input = document.querySelector(`input[data-var="${key}"]`);
    if (input) input.value = value;
  }
}

function resetThemePreview() {
  const stored = localStorage.getItem('focus-custom-theme');
  if (stored) {
    var theme;
    try { theme = JSON.parse(stored); } catch(e) { theme = {}; }
    for (const key in theme) document.documentElement.style.setProperty(key, theme[key]);
  } else {
    const vars = ['--accent', '--accent-hover', '--accent-dim', '--accent-faint'];
    document.querySelectorAll('#theme-color-pickers input[type="color"]').forEach((input) => {
      const varName = input.getAttribute('data-var');
      document.documentElement.style.removeProperty(varName);
    });
    vars.forEach((v) => document.documentElement.style.removeProperty(v));
  }
}

function saveCustomTheme() {
  const newTheme = {};
  document.querySelectorAll('#theme-color-pickers input[type="color"]').forEach((input) => {
    newTheme[input.getAttribute('data-var')] = input.value;
  });
  const accent = newTheme['--accent'];
  if (accent) {
    Object.assign(newTheme, computeAccentDerivatives(accent));
  }
  for (const [key, value] of Object.entries(newTheme)) {
    document.documentElement.style.setProperty(key, value);
  }
  localStorage.setItem('focus-custom-theme', JSON.stringify(newTheme));
  _saveThemeToApi(newTheme);
  closeModal('modal-themes');
}

// On load, try to load theme from API if localStorage is empty (fresh browser)
(function () {
  if (!localStorage.getItem('focus-custom-theme')) {
    fetch('/api/settings')
      .then(function (r) { return r.json(); })
      .then(function (settings) {
        if (settings.theme_json) {
          var theme = JSON.parse(settings.theme_json);
          localStorage.setItem('focus-custom-theme', JSON.stringify(theme));
          for (var key in theme) {
            document.documentElement.style.setProperty(key, theme[key]);
          }
        }
      })
      .catch(function () {});
  }
})();
