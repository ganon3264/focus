(function () {
  function formatTimestamps() {
    var els = document.querySelectorAll('[data-utc]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var utc = el.getAttribute('data-utc');
      if (!utc) continue;
      var d = new Date(utc);
      if (isNaN(d.getTime())) continue;
      var dateEl = el.querySelector('.ts-date');
      var timeEl = el.querySelector('.ts-time');
      if (dateEl) {
        dateEl.textContent = d.toLocaleDateString();
      }
      if (timeEl) {
        timeEl.textContent = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
    }
  }

  window.formatTimestamps = formatTimestamps;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', formatTimestamps);
  } else {
    formatTimestamps();
  }

  document.addEventListener('htmx:afterSettle', function (e) {
    if (e.detail.target && e.detail.target.closest('#message-list')) {
      formatTimestamps();
    }
  });
})();
