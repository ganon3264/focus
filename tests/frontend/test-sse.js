// Unit tests for sse.js — SSE reader + progress runner
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var fs = require('fs');
var path = require('path');

global.window = global;

function sseResponse(chunks) {
  return {
    ok: true,
    body: new ReadableStream({
      start: function (controller) {
        var enc = new TextEncoder();
        chunks.forEach(function (c) {
          controller.enqueue(enc.encode(c));
        });
        controller.close();
      },
    }),
    text: function () {
      return Promise.resolve('');
    },
  };
}

eval(
  fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'sse.js'), 'utf8'),
);

assert(typeof window.readEventStream === 'function', 'readEventStream loaded');
assert(typeof window.streamProgress === 'function', 'streamProgress loaded');

function run(url, opts, chunks) {
  global.fetch = function () {
    return Promise.resolve(sseResponse(chunks));
  };
  var events = [];
  return window.streamProgress(url, opts, function (ev) {
    events.push(ev);
  }).then(function (result) {
    return { result: result, events: events };
  });
}

// ── Progress events are dispatched, done payload is resolved ──
run('/api/x', {}, [
  'data: {"type":"progress","label":"Reading database","current":0,"total":0}\n\n',
  'data: {"type":"progress","label":"Archiving files","current":2,"total":5}\n\n',
  'data: {"type":"done","result":{"size_bytes":1234}}\n\n',
]).then(function (out) {
  assertEqual(out.events.length, 2, 'progress: two progress events dispatched');
  assertEqual(out.events[1].label, 'Archiving files', 'progress: label parsed');
  assertEqual(out.events[1].current, 2, 'progress: current parsed');
  assertEqual(out.result.size_bytes, 1234, 'progress: done result resolved');

  // ── Events split across chunk boundaries still parse ──
  return run('/api/x', {}, [
    'data: {"type":"prog',
    'ress","label":"Split"}\n\ndata: {"type":"done","result":{"ok":true}}\n\n',
  ]);
}).then(function (out) {
  assertEqual(out.events.length, 1, 'chunks: event split mid-payload');
  assertEqual(out.events[0].label, 'Split', 'chunks: label survives a split');
  assertEqual(out.result.ok, true, 'chunks: done result resolved');

  // ── An error event rejects, and stops before the rest of the stream ──
  global.fetch = function () {
    return Promise.resolve(
      sseResponse([
        'data: {"type":"progress","label":"Working"}\n\n',
        'data: {"type":"error","error":"disk full"}\n\n',
        'data: {"type":"done","result":{}}\n\n',
      ]),
    );
  };
  var seen = 0;
  return window
    .streamProgress('/api/x', {}, function () {
      seen++;
    })
    .then(function () {
      throw new Error('error event must reject');
    })
    .catch(function (e) {
      assertEqual(e.message, 'disk full', 'error: message surfaces');
      assertEqual(seen, 1, 'error: stops dispatching after the failure');
    });
}).then(function () {
  // ── A stream that ends without done rejects ──
  global.fetch = function () {
    return Promise.resolve(sseResponse(['data: {"type":"progress","label":"Working"}\n\n']));
  };
  return window
    .streamProgress('/api/x', {}, function () {})
    .then(function () {
      throw new Error('truncated stream must reject');
    })
    .catch(function (e) {
      assertEqual(e.message, 'Stream ended before the operation finished', 'truncated: rejects');
    });
}).then(function () {
  // ── HTTP failures surface the server's detail ──
  global.fetch = function () {
    return Promise.resolve({
      ok: false,
      body: null,
      text: function () {
        return Promise.resolve('{"detail":"Backup dir missing"}');
      },
    });
  };
  return window
    .streamProgress('/api/x', {}, function () {})
    .then(function () {
      throw new Error('HTTP failure must reject');
    })
    .catch(function (e) {
      assertEqual(e.message, 'Backup dir missing', 'http: detail surfaces');
    });
}).then(function () {
  // ── readEventStream: stops and cancels when the callback returns true ──
  var cancelled = false;
  var enc = new TextEncoder();
  var body = new ReadableStream({
    pull: function (controller) {
      controller.enqueue(
        enc.encode('data: {"type":"a"}\n\ndata: {"type":"b"}\n\ndata: {"type":"c"}\n\n'),
      );
    },
    cancel: function () {
      cancelled = true;
    },
  });
  var seen = [];
  return window
    .readEventStream({ body: body }, function (ev) {
      seen.push(ev.type);
      return ev.type === 'b';
    })
    .then(function () {
      assertEqual(seen.join(''), 'ab', 'readEventStream: stops at the first true');
      assert(cancelled, 'readEventStream: cancels a stopped stream');
      h.printSummary();
    });
});
