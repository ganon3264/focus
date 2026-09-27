// ── Skin manager ─────────────────────────────────────────────────────────────
// Skin = interface structure; theme = colour. Skins are plain CSS overlays in
// static/css/skins/*.css, every rule gated on [data-skin="<id>"] on <html>.
// The default (classic) is server-rendered in base.html; the stored choice is
// applied pre-paint by the inline hook there. This module owns runtime swaps:
// attribute → persist → skin-changed event → toast.

window.SKINS = [
  { id: 'instrument', label: 'Instrument', description: 'Hairline structure, quiet labels, mono readouts' },
  { id: 'classic', label: 'Classic', description: 'Soft surfaces, rounded corners, elevation' },
];

window.SkinManager = (function () {
  var STORAGE_KEY = 'focus-skin';
  var DEFAULT_SKIN = 'classic';

  function find(id) {
    for (var i = 0; i < window.SKINS.length; i++) {
      if (window.SKINS[i].id === id) return window.SKINS[i];
    }
    return null;
  }

  function get() {
    var id = null;
    try {
      id = window.localStorage.getItem(STORAGE_KEY);
    } catch (e) {}
    return find(id) ? id : DEFAULT_SKIN;
  }

  function set(id) {
    var skin = find(id);
    if (!skin) return;
    apply(skin.id);
    try {
      window.localStorage.setItem(STORAGE_KEY, skin.id);
    } catch (e) {}
    window.dispatchEvent(new CustomEvent('skin-changed', { detail: { id: skin.id } }));
    window.showToast('Skin: ' + skin.label);
  }

  function apply(id) {
    document.documentElement.setAttribute('data-skin', id || get());
  }

  apply();

  return { get: get, set: set, apply: apply };
})();
