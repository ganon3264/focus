const PRESET_THEMES = {
  default: {
    '--bg': '#0b0d10', '--surface': '#13151a', '--surface-2': '#1c1f26', '--surface-3': '#2b303b',
    '--border': '#232730', '--accent': '#6366f1', '--text': '#f1f3f5', '--text-muted': '#8b949e'
  },
  midnight: {
    '--bg': '#000000', '--surface': '#090909', '--surface-2': '#111111', '--surface-3': '#1a1a1a',
    '--border': '#222222', '--accent': '#3b82f6', '--text': '#ffffff', '--text-muted': '#9ca3af'
  },
  light: {
    '--bg': '#f8fafc', '--surface': '#ffffff', '--surface-2': '#f1f5f9', '--surface-3': '#e2e8f0',
    '--border': '#e2e8f0', '--accent': '#4f46e5', '--text': '#0f172a', '--text-muted': '#64748b'
  }
};

let _savedThemeBackup = {};

const _themeTrigger = document.querySelector('[onclick="openModal(\'modal-themes\')"]');
if (_themeTrigger) {
  _themeTrigger.addEventListener('click', function () {
    _savedThemeBackup = {};
    const rootStyle = getComputedStyle(document.documentElement);
    document.querySelectorAll('#theme-color-pickers input[type="color"]').forEach(input => {
      const varName = input.getAttribute('data-var');
      let color = rootStyle.getPropertyValue(varName).trim();
      if (color.startsWith('rgba')) { color = '#000000'; }
      if (color.length === 4) { color = '#' + color[1]+color[1]+color[2]+color[2]+color[3]+color[3]; }
      input.value = color || '#000000';
      _savedThemeBackup[varName] = color;
    });
  });
}

function previewThemeColor(input) {
  document.documentElement.style.setProperty(input.getAttribute('data-var'), input.value);
}

function applyPresetTheme(presetName) {
  const theme = PRESET_THEMES[presetName];
  if (!theme) return;
  localStorage.setItem('pyvern-custom-theme', JSON.stringify(theme));
  for (const [key, value] of Object.entries(theme)) {
    document.documentElement.style.setProperty(key, value);
    const input = document.querySelector(`input[data-var="${key}"]`);
    if (input) input.value = value;
  }
}

function resetThemePreview() {
  const stored = localStorage.getItem('pyvern-custom-theme');
  if (stored) {
    const theme = JSON.parse(stored);
    for (const key in theme) document.documentElement.style.setProperty(key, theme[key]);
  } else {
    document.querySelectorAll('#theme-color-pickers input[type="color"]').forEach(input => {
      document.documentElement.style.removeProperty(input.getAttribute('data-var'));
    });
  }
}

function saveCustomTheme() {
  const newTheme = {};
  document.querySelectorAll('#theme-color-pickers input[type="color"]').forEach(input => {
    newTheme[input.getAttribute('data-var')] = input.value;
  });
  localStorage.setItem('pyvern-custom-theme', JSON.stringify(newTheme));
  closeModal('modal-themes');
}
