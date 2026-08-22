// Unit tests for the stop-button escalation ladder (contract test).
//
// The stop flow is a two-stage escalation:
//   1. Graceful: POST /api/stop-generation/{id} (with its own timeout) and
//      wait for the server's normal `done` SSE event.
//   2. Forced: if the POST fails/times out, or `done` doesn't arrive within
//      STOP_DRAIN_TIMEOUT_MS, the stream is hard-aborted client-side.
//
// The new contract:
//   Click stop        → info feedback toast + stop POST + drain watchdog armed
//   POST fails        → immediate hard abort + resolution toast, watchdog cleared
//   done arrives      → watchdog cleared + resolution toast
//   done never comes  → watchdog fires → hard abort + resolution toast

var h = require('./helpers.js');
var assert = h.assert;

var STOP_POST_TIMEOUT_MS = 4000;
var STOP_DRAIN_TIMEOUT_MS = 8000;

// ── Replicate the production escalation ladder ──
function makeStopFlow() {
  var log = [];
  var pendingStop = null;
  var now = 0;
  var timers = [];

  function setTimeoutAt(fn, ms) {
    timers.push({ at: now + ms, fn: fn });
    timers.sort(function (a, b) { return a.at - b.at; });
  }

  function clearPendingStop() {
    if (pendingStop) {
      pendingStop = null;
    }
  }

  function advance(ms) {
    var target = now + ms;
    while (timers.length && timers[0].at <= target) {
      now = timers[0].at;
      var t = timers.shift();
      if (!t.fn.cancelled) t.fn();
    }
    now = target;
  }

  return {
    log: log,
    advance: advance,
    click: function () {
      if (pendingStop) return;
      log.push('toast:info Stopping generation…');
      // stop POST — simulated by caller calling .postResult(ok)
      var self = this;
      setTimeoutAt(function () {
        if (self.postOk === false) {
          clearPendingStop();
          self.aborted = true;
          log.push('abort');
          log.push('toast:success Generation stopped');
        }
      }, STOP_POST_TIMEOUT_MS);
      // drain watchdog
      setTimeoutAt(function () {
        if (!pendingStop) return;
        pendingStop = null;
        self.aborted = true;
        log.push('abort');
        log.push('toast:success Generation stopped');
      }, STOP_DRAIN_TIMEOUT_MS);
      pendingStop = { timer: true };
    },
    postOk: null,
    aborted: false,
    serverDone: function () {
      if (!pendingStop) return;
      clearPendingStop();
      log.push('toast:success Generation stopped');
    },
  };
}

// ── Tests ──

(function () {
  // 1. Click shows immediate feedback and arms the watchdog
  var f1 = makeStopFlow();
  f1.click();
  assert(f1.log[0] === 'toast:info Stopping generation…', 'click: info toast shown immediately');
  assert(!f1.aborted, 'click: nothing aborted yet');

  // 2. Server confirms in time → resolution toast, no forced abort
  f1.serverDone();
  assert(
    f1.log.indexOf('toast:success Generation stopped') !== -1,
    'graceful: resolution toast on done',
  );
  f1.advance(STOP_DRAIN_TIMEOUT_MS + 1000);
  assert(!f1.aborted, 'graceful: watchdog did not fire after confirmation');

  // 3. Stop POST hangs/fails → hard abort at post timeout
  var f3 = makeStopFlow();
  f3.postOk = false;
  f3.click();
  f3.advance(STOP_POST_TIMEOUT_MS + 1000);
  assert(f3.aborted, 'post failure: stream force-aborted');
  assert(
    f3.log.indexOf('toast:success Generation stopped') !== -1,
    'post failure: resolution toast shown',
  );

  // 4. POST ok but done never arrives → watchdog force-aborts
  var f4 = makeStopFlow();
  f4.postOk = true;
  f4.click();
  f4.advance(STOP_DRAIN_TIMEOUT_MS - 1000);
  assert(!f4.aborted, 'watchdog: patient before deadline');
  f4.advance(2000);
  assert(f4.aborted, 'watchdog: hard abort after drain deadline');
  assert(
    f4.log.indexOf('toast:success Generation stopped') !== -1,
    'watchdog: resolution toast shown',
  );

  // 5. Double click is a no-op while escalation is pending
  var f5 = makeStopFlow();
  f5.click();
  var logLen = f5.log.length;
  f5.click();
  assert(f5.log.length === logLen, 'double click: ignored while pending');
})();

// ── Result ──
h.printSummary();
