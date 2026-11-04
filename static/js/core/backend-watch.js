(function () {
  var CHECK_URL = '/api/health';
  var POLL_MS = 3000;
  var PROBE_TIMEOUT_MS = 2500;

  var offline = false;
  var timer = null;
  var probing = false;
  var nativeFetch = window.fetch.bind(window);

  function lock() {
    var el = document.getElementById('backend-offline');
    if (el) el.classList.remove('hidden');
    Array.prototype.forEach.call(document.body.children, function (child) {
      if (child.tagName === 'SCRIPT' || child.id === 'backend-offline' || child.id === 'toast-container') return;
      child.setAttribute('inert', '');
    });
    offline = true;
    if (!timer) timer = setInterval(probe, POLL_MS);
  }

  function unlock() {
    var el = document.getElementById('backend-offline');
    if (el) el.classList.add('hidden');
    Array.prototype.forEach.call(document.body.children, function (child) {
      child.removeAttribute('inert');
    });
    offline = false;
    clearInterval(timer);
    timer = null;
  }

  function probe() {
    if (probing) return;
    probing = true;
    var ctrl = window.AbortController ? new AbortController() : null;
    var timeout = ctrl ? setTimeout(function () { ctrl.abort(); }, PROBE_TIMEOUT_MS) : null;
    nativeFetch(CHECK_URL, { cache: 'no-store', signal: ctrl ? ctrl.signal : undefined })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        if (offline) unlock();
      })
      .catch(function () {
        if (!offline) lock();
      })
      .finally(function () {
        clearTimeout(timeout);
        probing = false;
      });
  }

  window.BackendWatch = {
    check: probe,
    isOffline: function () { return offline; },
  };

  document.addEventListener('htmx:sendError', probe, true);
  document.addEventListener('htmx:timeout', probe, true);
  window.addEventListener('offline', probe);
  window.addEventListener('online', probe);
  window.addEventListener('keydown', function (evt) {
    if (offline) evt.stopImmediatePropagation();
  }, true);

  window.fetch = function () {
    return nativeFetch.apply(window, arguments).catch(function (err) {
      if (!err || err.name !== 'AbortError') probe();
      throw err;
    });
  };
})();
