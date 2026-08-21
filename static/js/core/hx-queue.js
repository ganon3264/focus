(function () {
  // htmx.ajax() calls share document.body as their request source, and htmx
  // serializes concurrent requests per-source with a "last wins" queue. That
  // silently drops earlier reloads. All programmatic partial reloads should
  // go through hxGet/hxPost so they are serialized and never dropped.
  var tail = Promise.resolve();

  function enqueue(fn) {
    var run = tail.then(fn, fn);
    tail = run.then(
      function () {},
      function () {},
    );
    return run;
  }

  window.hxQueue = enqueue;
  window.hxGet = function (url, opts) {
    return enqueue(function () {
      return htmx.ajax('GET', url, opts);
    });
  };
  window.hxPost = function (url, opts) {
    return enqueue(function () {
      return htmx.ajax('POST', url, opts);
    });
  };
})();
