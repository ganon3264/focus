(function () {
  // htmx serializes requests per *source element*, and the default policy is
  // "last wins": while a request from that source is in flight, a newer one
  // replaces the pending queue, so the pending request never happens — no
  // error, no event, no log. htmx.ajax() with no source defaults to
  // document.body, which every programmatic reload in the app would share.
  //
  // So hxGet/hxPost issue from one dedicated source carrying
  // `hx-sync="this:queue all"`: a request that arrives while another is in
  // flight is queued behind it instead of replacing it. The queue below keeps
  // them ordered (writes must commit in order); hx-sync is the safety net for
  // the case where htmx resolves the ajax promise before it has really sent
  // anything (any early-out branch: a cancelled confirm, a validation halt).
  var tail = Promise.resolve();

  function enqueue(fn) {
    var run = tail.then(fn, fn);
    tail = run.then(
      function () {},
      function () {},
    );
    return run;
  }

  function source() {
    var el = document.getElementById('hx-source');
    if (el) return el;
    el = document.createElement('div');
    el.id = 'hx-source';
    el.className = 'hidden';
    el.setAttribute('aria-hidden', 'true');
    el.setAttribute('hx-sync', 'this:queue all');
    document.body.appendChild(el);
    return el;
  }

  function from(_opts) {
    var opts = { source: source() };
    if (_opts && typeof _opts === 'object') {
      for (var key in _opts) {
        if (_opts.hasOwnProperty(key)) opts[key] = _opts[key];
      }
    } else if (_opts !== undefined) {
      opts.target = _opts;
    }
    return opts;
  }

  window.hxQueue = enqueue;
  window.hxGet = function (url, opts) {
    return enqueue(function () {
      return htmx.ajax('GET', url, from(opts));
    });
  };
  window.hxPost = function (url, opts) {
    return enqueue(function () {
      return htmx.ajax('POST', url, from(opts));
    });
  };
  window.hxFetch = function (url, opts) {
    return enqueue(function () {
      return fetch(url, opts);
    });
  };
})();
