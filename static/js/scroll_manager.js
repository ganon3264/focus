(function () {
  window.autoScroll = true;
  window.scrollSentinel = null;

  window.ensureSentinelAndObserver = function () {
    const ml = document.getElementById('message-list');
    const cc = document.querySelector('.chat-center');
    if (!ml || !cc) return;

    let s = document.getElementById('scroll-sentinel');
    if (!s) {
      s = document.createElement('div');
      s.id = 'scroll-sentinel';
      s.style.height = '1px';
      ml.appendChild(s);
    } else if (ml.lastChild !== s) {
      ml.appendChild(s);
    }
    window.scrollSentinel = s;

    if (window._scrollObserver) window._scrollObserver.disconnect();
    window._scrollObserver = new IntersectionObserver(
      function (_ref) {
        window.autoScroll = _ref[0].isIntersecting;
      },
      { root: cc, threshold: 0 },
    );
    window._scrollObserver.observe(s);
  };

  function scrollToBottom() {
    var navEntries = performance.getEntriesByType('navigation');
    if (navEntries.length > 0 && navEntries[0].type === 'navigate') {
      requestAnimationFrame(function () {
        requestAnimationFrame(function () {
          var s = document.getElementById('scroll-sentinel');
          if (s) s.scrollIntoView({ block: 'end' });
        });
      });
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    window.ensureSentinelAndObserver();
    scrollToBottom();
  });
})();
