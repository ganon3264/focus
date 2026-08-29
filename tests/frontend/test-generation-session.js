// Contract tests for the real generation session (core/generation-session.js +
// messages/stream-events.js) driven against a scriptable SSE response.
//
// These load the two production modules verbatim into a vm sandbox and only
// mock their environment (DOM, fetch, toasts, refresh), so the assertions hold
// against the real lifecycle code:
//   - begin() always settles, even when the transport misbehaves
//   - the session is idle again once begin() settles
//   - a failed generation never leaves a spinner-bearing node behind

var fs = require('fs');
var path = require('path');
var vm = require('vm');
var h = require('./helpers.js');
var failed = 0;
function assert(cond, msg) {
  if (cond) { console.log('  ok   ' + msg); }
  else { failed++; console.error('  FAIL ' + msg); }
}

var ROOT = path.join(__dirname, '..', '..');
var MODULES = [
  'static/js/messages/stream-events.js',
  'static/js/core/generation-session.js',
];

// ── Assistant node factory (mirrors buildAssistantSkeleton's shape) ──
function newAssistant(id) {
  var d = h.makeElement('div');
  d.classList.add('message');
  if (id) d.id = id;
  var body = h.makeElement('div');
  body.classList.add('message-body');
  var content = h.makeElement('div');
  content.classList.add('message-content');
  body.appendChild(content);
  d.appendChild(body);
  return d;
}

// ── Environment ──
function makeEnv() {
  var doc = h.createMockDocument();
  var messageList = h.makeElement('div');
  messageList.id = 'message-list';
  var sentinel = h.makeElement('div');
  sentinel.id = 'scroll-sentinel';
  messageList.appendChild(sentinel);
  doc.body.appendChild(messageList);

  var env = {
    toasts: [],
    refreshes: [],
    generatingUI: [],
    listFetches: [],
  };

  var sandbox = {
    console: {
      log: function () { if (process.env.DEBUG_JS) console.log('[sandbox]', ...arguments); },
      warn: function () { if (process.env.DEBUG_JS) console.warn('[sandbox]', ...arguments); },
      error: function () { if (process.env.DEBUG_JS) console.error('[sandbox]', ...arguments); },
    },
    document: doc,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
    JSON: JSON,
    Math: Math,
    Date: Date,
    Array: Array,
    Object: Object,
    String: String,
    Number: Number,
    Boolean: Boolean,
    Error: Error,
    TypeError: TypeError,
    Promise: Promise,
    TextEncoder: TextEncoder,
    TextDecoder: TextDecoder,
    ReadableStream: ReadableStream,
    AbortController: AbortController,
    requestAnimationFrame: function (fn) { return setTimeout(fn, 0); },
    cancelAnimationFrame: function (id) { clearTimeout(id); },
    StateManager: { get: function () { return 'prov-1'; } },
    api: {
      stream: '/api/stream',
      partials: { messageList: function (id) { return '/partials/message-list/' + id; } },
    },
    hxGet: function (url) {
      env.listFetches.push(url);
      return Promise.resolve();
    },
    showErrorToast: function (m) { env.toasts.push({ type: 'error', msg: m }); },
    showSuccessToast: function (m) { env.toasts.push({ type: 'success', msg: m }); },
    showInfoToast: function (m) { env.toasts.push({ type: 'info', msg: m }); },
    hideErrorToast: function () {},
    hideInfoToast: function () {},
    setGeneratingUI: function (on) { env.generatingUI.push(on); },
    clearStaleContent: function () {},
    uploadStagedAttachments: function () { return Promise.resolve([]); },
    refreshMessagesAfterStream: function (chatId, userId, asstId) {
      env.refreshes.push(asstId);
      return Promise.resolve();
    },
    refreshChatMessages: function (chatId) {
      env.refreshes.push('list');
      return Promise.resolve();
    },
    renderMessage: function (t) { return t; },
    preserveOpenStates: function (el, fn) { el.innerHTML = fn(); },
    _updateReasoningButton: function () {},
    syncReasoningButtons: function () {},
    buildAssistantSkeleton: function () { return newAssistant('skeleton'); },
    segmentBuilders: {
      text: function () { var d = h.makeElement('div'); d.classList.add('message-content'); return d; },
      reasoning: function () {
        var d = h.makeElement('div');
        d.classList.add('reasoning-block');
        var rc = h.makeElement('div');
        rc.classList.add('reasoning-content');
        d.appendChild(rc);
        return d;
      },
      tool_calls: function () { return h.makeElement('div'); },
    },
    updateToolCallCard: function () {},
    scrollSentinel: sentinel,
  };
  sandbox.window = sandbox;
  vm.createContext(sandbox);
  MODULES.forEach(function (rel) {
    vm.runInContext(fs.readFileSync(path.join(ROOT, rel), 'utf8'), sandbox, { filename: rel });
  });

  env.sandbox = sandbox;
  env.Generation = sandbox.window.Generation;
  env.messageList = messageList;
  env.doc = doc;
  return env;
}

// A Response whose body is driven by `steps`:
//   {data: obj} | {raw: string} | {close: true} | {error: Error} | {stall: true}
function sseResponse(steps, signal) {
  var encoder = new TextEncoder();
  var i = 0;
  var body = new ReadableStream({
    pull: function (controller) {
      if (signal && signal.aborted) {
        controller.error(mkAbort());
        return;
      }
      if (i >= steps.length) { controller.close(); return; }
      var s = steps[i++];
      if (s.stall) {
        // Leave the stream open with nothing more coming; a abort listener
        // mirrors how a real fetch body reacts to controller.abort().
        if (signal) {
          signal.addEventListener('abort', function () {
            try { controller.error(mkAbort()); } catch (e) { /* already errored */ }
          });
        }
        return;
      }
      if (s.error) { controller.error(s.error); return; }
      if (s.close) { controller.close(); return; }
      if (s.data) controller.enqueue(encoder.encode('data: ' + JSON.stringify(s.data) + '\n\n'));
      if (s.raw) controller.enqueue(encoder.encode(s.raw));
    },
  });
  return {
    ok: true,
    status: 200,
    body: body,
    text: function () { return Promise.resolve(''); },
    json: function () { return Promise.resolve({}); },
  };
}

function mkAbort() {
  var e = new Error('The operation was aborted.');
  e.name = 'AbortError';
  return e;
}

// Drive one generation; resolves with {settled, error} once begin() settles or
// the watchdog fires (a stuck lifecycle must fail, not hang CI).
function drive(env, steps, opts, extraFetch) {
  var asst = newAssistant('streaming-message');
  env.messageList.appendChild(asst);
  env.sandbox.fetch = extraFetch || function (url, reqOpts) {
    if (url === '/api/stream') {
      return Promise.resolve(sseResponse(steps, reqOpts && reqOpts.signal));
    }
    return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(''); } });
  };
  var out = { settled: false, error: null };
  var done = env.Generation.begin('chat-1', asst, opts || {}).then(
    function () { out.settled = true; },
    function (e) { out.settled = true; out.error = e; }
  );
  out.asst = asst;
  out.promise = done;
  return new Promise(function (resolve) {
    var watchdog = setTimeout(function () {
      if (!out.settled) resolve(out);
    }, 1500);
    done.then(function () { clearTimeout(watchdog); resolve(out); });
  });
}

// A stream that sends `start` and then never sends anything else.
function stalledStream(url, reqOpts, startMessageId) {
  var signal = reqOpts && reqOpts.signal;
  return {
    ok: true,
    status: 200,
    body: new ReadableStream({
      start: function (controller) {
        var payload = { type: 'start', message_id: startMessageId || 'm1', user_message_id: 'u1' };
        controller.enqueue(new TextEncoder().encode('data: ' + JSON.stringify(payload) + '\n\n'));
        if (signal) {
          signal.addEventListener('abort', function () {
            try { controller.error(mkAbort()); } catch (e) { /* already closed */ }
          });
        }
      },
    }),
  };
}

var tests = [];
function test(name, fn) { tests.push({ name: name, fn: fn }); }

test('provider error releases the session', function () {
  var env = makeEnv();
  return drive(env, [
    { data: { type: 'start', message_id: 'm1', user_message_id: 'u1' } },
    { data: { type: 'error', error: 'Insufficient Credits' } },
  ]).then(function (r) {
    assert(r.settled, 'begin() settles after a provider error');
    assert(!r.error, 'no unhandled rejection after a provider error');
    assert(!env.Generation.isActive(), 'session is idle after a provider error');
    assert(env.generatingUI[env.generatingUI.length - 1] === false, 'send button restored');
    assert(env.toasts.some(function (t) { return t.type === 'error' && t.msg === 'Insufficient Credits'; }),
      'provider error is surfaced as a toast');
    assert(r.asst.parentNode === null, 'failed assistant node is removed from the list');
    assert(env.refreshes.indexOf('list') >= 0, 'message list is refetched once');
  });
});

test('HTTP failure releases the session', function () {
  var env = makeEnv();
  return drive(env, [], null, function (url) {
    if (url === '/api/stream') {
      return Promise.resolve({ ok: false, status: 502, text: function () { return Promise.resolve('Bad gateway'); } });
    }
    return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(''); } });
  }).then(function (r) {
    assert(r.settled, 'begin() settles on a non-2xx response');
    assert(!env.Generation.isActive(), 'session is idle after an HTTP failure');
    assert(env.toasts.length > 0, 'HTTP failure is surfaced as a toast');
  });
});

test('stream truncated without done releases the session', function () {
  var env = makeEnv();
  return drive(env, [
    { data: { type: 'start', message_id: 'm1', user_message_id: 'u1' } },
    { data: { type: 'token', text: 'partial ' } },
    { data: { type: 'token', text: 'answer' } },
  ]).then(function (r) {
    assert(r.settled, 'begin() settles when the server stops without done');
    assert(!env.Generation.isActive(), 'session is idle after a truncated stream');
    assert(env.refreshes.indexOf('m1') >= 0, 'post-stream refresh ran for a truncated stream');
  });
});

test('error event mid-stream releases the session', function () {
  var env = makeEnv();
  return drive(env, [
    { data: { type: 'start', message_id: 'm1', user_message_id: 'u1' } },
    { data: { type: 'token', text: 'partial ' } },
    { data: { type: 'error', error: 'connection reset by peer' } },
  ]).then(function (r) {
    assert(r.settled, 'begin() settles on a mid-stream error');
    assert(!env.Generation.isActive(), 'session is idle after a mid-stream error');
    assert(r.asst.parentNode === null, 'partially rendered node is removed');
  });
});

test('body read error releases the session', function () {
  var env = makeEnv();
  return drive(env, [
    { data: { type: 'start', message_id: 'm1', user_message_id: 'u1' } },
    { error: new TypeError('network error while reading body') },
  ]).then(function (r) {
    assert(r.settled, 'begin() settles when the body read blows up');
    assert(!env.Generation.isActive(), 'session is idle after a body read error');
  });
});

test('reader is cancelled when the stream is left early', function () {
  var env = makeEnv();
  var cancelled = false;
  var asst = newAssistant('streaming-message');
  env.messageList.appendChild(asst);
  env.sandbox.fetch = function (url, reqOpts) {
    if (url !== '/api/stream') {
      return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(''); } });
    }
    var encoder = new TextEncoder();
    return Promise.resolve({
      ok: true,
      status: 200,
      body: {
        getReader: function () {
          var sent = 0;
          return {
            read: function () {
              if (sent++ === 0) {
                return Promise.resolve({
                  done: false,
                  value: encoder.encode('data: ' + JSON.stringify({
                    type: 'error', error: 'Insufficient Credits',
                  }) + '\n\n'),
                });
              }
              // Never resolves: only cancel() (or close) can end the loop.
              return new Promise(function () {});
            },
            cancel: function () { cancelled = true; return Promise.resolve(); },
          };
        },
      },
    });
  };
  return Promise.race([
    env.Generation.begin('chat-1', asst, {}),
    new Promise(function (res) { setTimeout(res, 1000); }),
  ]).then(function () {
    assert(cancelled, 'response body is cancelled after an error event');
    assert(!env.Generation.isActive(), 'session is idle after cancelling the reader');
  });
});

test('failed regenerate keeps the message node and its content', function () {
  var env = makeEnv();
  // A regenerate reuses a server-rendered message: clearStaleContent wipes it.
  var existing = h.makeElement('div');
  existing.id = 'message-old';
  // Built from markup so the DOM shim can snapshot/restore innerHTML verbatim.
  existing.innerHTML = '<div class="message-body"><div class="message-content">Original reply</div></div>';
  env.messageList.appendChild(existing);
  env.sandbox.clearStaleContent = function (div) {
    var cs = div.querySelectorAll('.message-content');
    for (var i = 0; i < cs.length; i++) cs[i].remove();
    var spinner = h.makeElement('div');
    spinner.className = 'message-spinner';
    div.appendChild(spinner);
  };
  env.sandbox.fetch = function (url) {
    if (url === '/api/stream') {
      return Promise.resolve(sseResponse([
        { data: { type: 'start', message_id: 'm9' } },
        { data: { type: 'error', error: 'Insufficient Credits' } },
      ]));
    }
    return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(''); } });
  };
  return env.Generation.begin('chat-1', existing, { isRegen: true }).then(function () {
    assert(existing.parentNode !== null, 'regenerate failure keeps the message in the list');
    assert(existing.querySelector('.message-spinner') === null, 'spinner removed after failure');
    assert(existing.querySelector('.message-content') !== null,
      'previous content restored after failed regenerate');
    assert(env.refreshes.indexOf('list') >= 0, 'failed regenerate re-renders the list');
  });
});

test('completed stream removes its own spinner', function () {
  var env = makeEnv();
  env.sandbox.clearStaleContent = function (div) {
    var spinner = h.makeElement('div');
    spinner.className = 'message-spinner';
    div.appendChild(spinner);
  };
  return drive(env, [
    { data: { type: 'start', message_id: 'm1', user_message_id: 'u1' } },
    { data: { type: 'token', text: 'hi' } },
    { data: { type: 'done', message_id: 'm1' } },
  ]).then(function (r) {
    assert(r.asst.querySelector('.message-spinner') === null,
      'spinner is gone as soon as the stream is over');
  });
});

test('server answering for another message triggers a full list refresh', function () {
  var env = makeEnv();
  var existing = newAssistant('message-old');
  existing.dataset.messageId = 'old-1';
  env.messageList.appendChild(existing);
  env.sandbox.fetch = function (url) {
    if (url === '/api/stream') {
      return Promise.resolve(sseResponse([
        { data: { type: 'start', message_id: 'different-1' } },
        { data: { type: 'token', text: 'hi' } },
        { data: { type: 'done', message_id: 'different-1' } },
      ]));
    }
    return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(''); } });
  };
  return env.Generation.begin('chat-1', existing, { isRegen: true }).then(function () {
    assert(env.refreshes.indexOf('list') >= 0,
      'identity mismatch re-renders the whole list');
    assert(env.refreshes.indexOf('different-1') === -1,
      'single-node refresh skipped when identities diverge');
  });
});

test('stop resolves at once when the generation is already gone (404)', function () {
  var env = makeEnv();
  var asst = newAssistant('streaming-message');
  env.messageList.appendChild(asst);
  env.sandbox.fetch = function (url, reqOpts) {
    if (url === '/api/stream') return stalledStream(url, reqOpts);
    return Promise.resolve({ ok: false, status: 404, text: function () { return Promise.resolve('nope'); } });
  };
  var settled = false;
  env.Generation.begin('chat-1', asst, {}).then(function () { settled = true; });
  return new Promise(function (res) { setTimeout(res, 30); })
    .then(function () { env.Generation.stop(); })
    .then(function () { return new Promise(function (res) { setTimeout(res, 300); }); })
    .then(function () {
      assert(settled, '404 from the stop endpoint ends the session without waiting for done');
      assert(env.toasts.some(function (t) { return t.type === 'success'; }), 'stop is reported');
      assert(!env.Generation.isActive(), 'session is idle after a 404 stop');
    });
});

test('stop before the start event still reports itself', function () {
  var env = makeEnv();
  var asst = newAssistant('streaming-message');
  env.messageList.appendChild(asst);
  env.sandbox.fetch = function (url, reqOpts) {
    if (url !== '/api/stream') return Promise.resolve({ ok: true, status: 200 });
    var signal = reqOpts.signal;
    return Promise.resolve({
      ok: true,
      status: 200,
      body: new ReadableStream({
        start: function (controller) {
          signal.addEventListener('abort', function () {
            try { controller.error(mkAbort()); } catch (e) { /* already closed */ }
          });
        },
      }),
    });
  };
  var settled = false;
  env.Generation.begin('chat-1', asst, {}).then(function () { settled = true; });
  return new Promise(function (res) { setTimeout(res, 30); })
    .then(function () { env.Generation.stop(); })
    .then(function () { return new Promise(function (res) { setTimeout(res, 200); }); })
    .then(function () {
      assert(settled, 'stop with no message id aborts the stream');
      assert(env.toasts.some(function (t) { return t.type === 'success'; }),
        'stop with no message id is reported');
    });
});

test('stalled stream: stop() escalation must release the session', function () {
  var env = makeEnv();
  var aborted = false;
  var asst = newAssistant('streaming-message');
  env.messageList.appendChild(asst);
  env.sandbox.fetch = function (url, reqOpts) {
    if (url !== '/api/stream') {
      return Promise.resolve({ ok: true, status: 200, text: function () { return Promise.resolve(''); } });
    }
    var signal = reqOpts.signal;
    return Promise.resolve({
      ok: true, status: 200,
      body: new ReadableStream({
        start: function (controller) {
          controller.enqueue(new TextEncoder().encode(
            'data: ' + JSON.stringify({ type: 'start', message_id: 'm1', user_message_id: 'u1' }) + '\n\n'));
          signal.addEventListener('abort', function () {
            aborted = true;
            try { controller.error(mkAbort()); } catch (e) { /* already closed */ }
          });
        },
      }),
    });
  };
  var out = { settled: false };
  env.Generation.begin('chat-1', asst, {}).then(function () { out.settled = true; });
  return new Promise(function (res) { setTimeout(res, 30); })
    .then(function () { env.Generation.stop(); })
    .then(function () { return new Promise(function (res) { setTimeout(res, 9000); }); })
    .then(function () {
      assert(aborted, 'drain watchdog force-aborts a stalled stream');
      assert(out.settled, 'session settles after stop escalation');
      assert(!env.Generation.isActive(), 'session is idle after stop escalation');
    });
});

(function run() {
  var idx = 0;
  function next() {
    if (idx >= tests.length) {
      console.log('\n' + (failed ? failed + ' test(s) FAILED' : 'all passed'));
      process.exit(failed ? 1 : 0);
    }
    var t = tests[idx++];
    console.log('— ' + t.name);
    var p = Promise.resolve().then(t.fn);
    var hang = new Promise(function (res) {
      setTimeout(function () {
        console.error('HANG: ' + t.name);
        res();
      }, 20000);
    });
    Promise.race([p, hang]).catch(function (e) {
      failed++;
      console.error('THREW: ' + t.name + ' — ' + (e && e.stack ? e.stack : e));
    }).then(next);
  }
  next();
})();
