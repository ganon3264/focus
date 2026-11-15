(function () {
  function formatTimestamps() {
    var clock = window.Prefs ? window.Prefs.get('clock') : '24h';
    if (clock === 'hidden') return;

    var els = document.querySelectorAll('[data-utc]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var utc = el.getAttribute('data-utc');
      if (!utc) continue;
      var d = new Date(utc);
      if (isNaN(d.getTime())) continue;
      var timeEl = el.querySelector('[data-ui="ts-time"]');
      if (timeEl) {
        timeEl.textContent = d.toLocaleTimeString([], {
          hour: '2-digit',
          minute: '2-digit',
          hour12: clock === '12h',
        });
      }
    }
  }

  window.formatTimestamps = formatTimestamps;

  window.addEventListener('prefs-changed', function (e) {
    if (e.detail.key === 'clock') formatTimestamps();
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', formatTimestamps);
  } else {
    formatTimestamps();
  }
})();
