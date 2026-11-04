(function () {
  var SLOW_MS = 4000;
  var STUCK_MS = 12000;
  var SLOW_TEXT = 'Still loading…';
  var STUCK_TEXT = 'Still waiting for a response. Is the app still running?';
  var ERROR_TEXT = 'Could not reach the backend. Is the app still running?';

  var tracked = new WeakMap();

  function isMarked(el) {
    return el && el.nodeType === 1 && el.matches('[data-ui="loading"]');
  }

  function placeholders(scope) {
    var found = [];
    if (!scope || scope.nodeType !== 1) return found;
    if (isMarked(scope)) found.push(scope);
    scope.querySelectorAll('[data-ui="loading"]').forEach(function (el) {
      found.push(el);
    });
    return found;
  }

  function clear(entry) {
    clearTimeout(entry.slow);
    clearTimeout(entry.stuck);
  }

  function start(el) {
    stop(el);
    var entry = { text: el.textContent };
    entry.slow = setTimeout(function () {
      if (el.isConnected) el.textContent = SLOW_TEXT;
    }, SLOW_MS);
    entry.stuck = setTimeout(function () {
      if (el.isConnected) el.textContent = STUCK_TEXT;
    }, STUCK_MS);
    tracked.set(el, entry);
  }

  function stop(el) {
    var entry = tracked.get(el);
    if (!entry) return;
    clear(entry);
    if (el.isConnected) {
      var text = el.textContent.trim();
      if (text === SLOW_TEXT || text === STUCK_TEXT) el.textContent = entry.text;
    }
    tracked.delete(el);
  }

  function fail(el) {
    var entry = tracked.get(el);
    if (!entry) return;
    clear(entry);
    if (el.isConnected) el.textContent = ERROR_TEXT;
  }

  function settle(evt) {
    var offline = evt.detail.xhr && evt.detail.xhr.status === 0;
    placeholders(evt.detail.target).forEach(offline ? fail : stop);
  }

  document.addEventListener('htmx:beforeRequest', function (evt) {
    placeholders(evt.detail.target).forEach(start);
  });

  document.addEventListener('htmx:afterRequest', settle);
})();
