(function () {
  if (window.readEventStream) return;

  // Read an SSE response body and hand each parsed `data:` payload to
  // `onPayload`. Returning true from the callback stops reading and cancels
  // the stream — an early exit must hand the connection back rather than leave
  // the server writing into a body nobody drains. Resolves when the body ends;
  // rejects if the body itself errors (an abort from the caller's signal).
  window.readEventStream = function (response, onPayload) {
    var reader = response.body.getReader();
    var decoder = new TextDecoder();
    var buffer = '';
    var stopped = false;

    function dispatch(line) {
      if (stopped || line.indexOf('data: ') !== 0) return;
      var payload;
      try {
        payload = JSON.parse(line.slice(6).trim());
      } catch (e) {
        return;
      }
      if (onPayload(payload) === true) stopped = true;
    }

    function pump() {
      return reader.read().then(function (chunk) {
        if (chunk.done) return;
        buffer += decoder.decode(chunk.value, { stream: true });
        var blocks = buffer.split('\n\n');
        buffer = blocks.pop();
        blocks.forEach(function (block) {
          block.split('\n').forEach(dispatch);
        });
        if (stopped) return reader.cancel().catch(function () {});
        return pump();
      });
    }

    return pump();
  };

  // POST a request that answers with `progress | done | error` events and
  // dispatch the progress ones to `onEvent`. Resolves with the `done` event's
  // `result`; rejects on an error event or a stream that ends without one.
  window.streamProgress = function (url, opts, onEvent) {
    opts = opts || {};
    return fetch(url, {
      method: opts.method || 'POST',
      headers: opts.headers || {},
      body: opts.body,
      signal: opts.signal,
    }).then(function (res) {
      if (!res.ok || !res.body) {
        return res.text().then(function (text) {
          var msg = text;
          try {
            msg = JSON.parse(text).detail || text;
          } catch (e) {}
          throw new Error(msg || 'Request failed');
        });
      }

      var result = null;
      var failure = null;
      return window
        .readEventStream(res, function (data) {
          if (data.type === 'done') {
            result = data.result;
            return false;
          }
          if (data.type === 'error') {
            failure = data.error || 'Operation failed';
            return true;
          }
          if (onEvent) onEvent(data);
        })
        .then(function () {
          if (failure) throw new Error(failure);
          if (result === null) throw new Error('Stream ended before the operation finished');
          return result;
        });
    });
  };
})();
