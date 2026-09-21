// Pure SSE event layer: StreamState, HANDLERS table, dispatch, finalize.
// Lifecycle (fetch, stop escalation) lives in core/generation-session.js;
// this module never touches fetch/abort state. Handlers record outcomes on
// the state object instead of throwing — the session loop decides what to do.
(function () {
  var dbg = function () {};
  if (window.DEBUG) {
    dbg = function () { console.log('[stream]', Array.prototype.slice.call(arguments)); };
  }

  function _lastSegment(state) {
    return state.segments.length > 0 ? state.segments[state.segments.length - 1] : null;
  }

  function _appendSegment(state, type, el) {
    var prev = _lastSegment(state);
    if (prev && prev.el && prev.el.parentNode) {
      prev.el.parentNode.insertBefore(el, prev.el.nextSibling);
    } else {
      var bodyEl = state.asstDiv.querySelector('.message-body');
      if (bodyEl) bodyEl.appendChild(el);
    }
    state.segments.push({ type: type, el: el });
  }

  function _findOrCreateSegment(state, type, createFn) {
    var last = _lastSegment(state);
    if (last && last.type === type) return last;
    var el = createFn();
    _appendSegment(state, type, el);
    return state.segments[state.segments.length - 1];
  }

  // Mutable state container for one generation
  window.StreamState = function (chatId, asstDiv, isRegen, continueText, continueReasoning) {
    this.chatId = chatId;
    this.asstDiv = asstDiv;
    this.isRegen = isRegen;
    this.continueText = continueText || null;
    this.continueReasoning = continueReasoning || null;
    this.fullText = '';
    this.messageId = null;
    this.userMessageId = null;
    this.done = false;
    this.errorMsg = null;
    this.stopRequested = false;
    this.retryCount = 0;
    this.segments = [];
    this.controller = new AbortController();
  };

  // ── Identity adoption (shared by stream and non-stream paths) ──

  window.adoptUserMessageId = function (state) {
    if (!state.userMessageId || state.isRegen) return;
    var tempUserMsg = document.getElementById('temp-user-msg');
    if (tempUserMsg) {
      tempUserMsg.id = MessageIdentity.domId(state.userMessageId);
      tempUserMsg.dataset.messageId = state.userMessageId;
    }
  };

  window.bindAssistantIdentity = function (state) {
    if (!state.messageId) return;
    var known = state.asstDiv.dataset.messageId;
    // Reusing an existing node (regenerate/continue/swipe) that already belongs
    // to another message: the server answered for a row the DOM did not expect,
    // so a single-node refresh would not be enough to resynchronise.
    if (known && known !== String(state.messageId)) state.identityChanged = true;
    state.asstDiv.id = MessageIdentity.domId(state.messageId);
    state.asstDiv.dataset.messageId = state.messageId;
  };

  // ── Render coalescing: at most one markdown pass per frame ──
  var _rafId = null;

  function flushRenders(state) {
    _rafId = null;
    var firstRendered = null;
    for (var i = 0; i < state.segments.length; i++) {
      var seg = state.segments[i];
      if (seg.type === 'text' && seg.dirty) {
        window.preserveOpenStates(seg.el, function () { return window.renderMessage(seg.content); });
        seg.dirty = false;
        if (!firstRendered) firstRendered = seg.el;
      }
    }
    if (firstRendered && window._updateReasoningButton) window._updateReasoningButton(firstRendered);
    if (firstRendered && window.autoScroll && window.scrollSentinel) {
      window.scrollSentinel.scrollIntoView({ block: 'end', behavior: 'instant' });
    }
  }

  function scheduleFlush(state) {
    if (_rafId !== null) return;
    _rafId = requestAnimationFrame(function () { flushRenders(state); });
  }

  // ── Transparent-retry feedback ──
  // The server tells us how long it will wait before the next attempt; show
  // that as one live info toast (attempt, countdown, reason) rather than a
  // generic message that vanishes the moment the retry succeeds.
  var RETRY_TOAST_ID = 'gen-retry';
  var RETRY_KIND_LABELS = {
    rate_limit: 'Rate limit',
    server: 'Server error',
    timeout: 'Timeout / connection',
    auth: 'Authentication',
    bad_request: 'Bad request',
    payment: 'Payment required',
  };
  var _retry = null; // { deadline, attempt, max, kind, status, reason, timer }

  function _retryCodeLine() {
    var label = RETRY_KIND_LABELS[_retry.kind] || '';
    if (label && _retry.status) return 'HTTP ' + _retry.status + ' \u00b7 ' + label;
    if (label) return label;
    if (_retry.status) return 'HTTP ' + _retry.status;
    return '';
  }

  function _retryText() {
    if (!_retry) return '';
    var seconds = Math.max(0, Math.ceil((_retry.deadline - Date.now()) / 1000));
    var head = 'Retrying (' + _retry.attempt + '/' + _retry.max + ')';
    head += seconds > 0 ? ' in ' + seconds + 's' : ' in \u2026';
    var lines = [head];
    var code = _retryCodeLine();
    if (code) lines.push(code);
    if (_retry.reason) lines.push(_retry.reason);
    return lines.join('\n');
  }

  function _renderRetry() {
    if (_retry && window.showInfoToast) {
      window.showInfoToast(_retryText(), { id: RETRY_TOAST_ID, duration: 0, maxChars: 200 });
    }
  }

  function _stopRetryFeedback() {
    if (_retry && _retry.timer) clearInterval(_retry.timer);
    _retry = null;
  }

  // Dismiss the retry toast and stop its countdown. Safe to call at any point
  // (done/error/truncated stream/abort) so the timer can't outlive the run.
  window.resetRetryFeedback = function () {
    _stopRetryFeedback();
    if (window.hideToast) window.hideToast(RETRY_TOAST_ID);
  };

  function _startRetryFeedback(data) {
    _stopRetryFeedback();
    _retry = {
      deadline: Date.now() + (Math.max(0, Number(data.delay) || 0) * 1000),
      attempt: data.attempt || 1,
      max: data.max || 1,
      kind: data.kind || '',
      status: data.status != null ? data.status : null,
      reason: String(data.reason || '').split('\n')[0],
      timer: null,
    };
    _renderRetry();
    _retry.timer = setInterval(_renderRetry, 500);
  }

  // ── Handlers ──
  var HANDLERS = {};

  HANDLERS.start = function (state, data) {
    state.messageId = data.message_id;
    state.userMessageId = data.user_message_id;

    dbg('SSE start: message_id=%s, user_message_id=%s', data.message_id, data.user_message_id);

    window.adoptUserMessageId(state);
  };

  HANDLERS.tool_calls = function (state, data) {
    var el = window.segmentBuilders.tool_calls(data.calls);
    _appendSegment(state, 'tool_calls', el);
  };

  HANDLERS.tool_result = function (state, data) {
    var last = _lastSegment(state);
    if (!last || last.type !== 'tool_calls') return;
    window.updateToolCallCard(last.el, data.call_id, data.result, data.is_error, data.image_url);
  };

  HANDLERS.reasoning = function (state, data) {
    var seg = _findOrCreateSegment(state, 'reasoning', function () {
      var rcCount = 0;
      for (var i = 0; i < state.segments.length; i++) {
        if (state.segments[i].type === 'reasoning') rcCount++;
      }
      // index 0 is reserved for reasoning that arrived before any text or
      // tool call (header-controlled). Anything else gets an inline toggle
      // with a unique index (1, 2, ...).
      var hasPrecedingContent = rcCount === 0 && state.segments.some(function (s) { return s.type !== 'reasoning'; });
      var idx = (rcCount === 0 && !hasPrecedingContent) ? 0 : rcCount + 1;
      return window.segmentBuilders.reasoning(idx);
    });
    seg.text = (seg.text || '') + (data.text || '');
    var rc = seg.el.querySelector('.reasoning-content');
    if (rc) rc.textContent = seg.text;
    if (window._updateReasoningButton) window._updateReasoningButton(state.asstDiv);
  };

  // Only fields with stream_to_sse reach the wire; currently that's reasoning.
  HANDLERS.meta = function (state, data) {
    if (data.field === 'reasoning') HANDLERS.reasoning(state, data);
  };

  HANDLERS.token = function (state, data) {
    state.fullText += data.text;
    var seg = _findOrCreateSegment(state, 'text', function () {
      return window.segmentBuilders.text();
    });
    seg.content = (seg.content || '') + data.text;
    seg.dirty = true;
    scheduleFlush(state);
  };

  HANDLERS.done = function (state, data) {
    state.done = true;
    state.messageId = data.message_id;
    if (state.retryCount) {
      window.resetRetryFeedback();
      // A stopped run can land here via the server's stop terminal event; it is
      // not a recovery, so do not claim one.
      if (!state.stopRequested && window.showSuccessToast) {
        var attempts = state.retryCount;
        window.showSuccessToast(
          'Recovered after ' + attempts + ' retr' + (attempts === 1 ? 'y' : 'ies'),
          { duration: 2500 },
        );
      }
    }
    dbg('SSE done: message_id=%s', data.message_id);
  };

  // A generation_end extension ran and its result is surfaced as a toast.
  HANDLERS.extension = function (state, data) {
    (data.logs || []).forEach(function (log) {
      var msg = log.message || '';
      if (log.level === 'error') { if (window.showErrorToast) window.showErrorToast(msg); }
      else if (log.level === 'success') { if (window.showSuccessToast) window.showSuccessToast(msg); }
      else { if (window.showInfoToast) window.showInfoToast(msg); }
    });
    if (data.status === 'error') {
      if (window.showErrorToast) window.showErrorToast(data.error || (data.name + ' failed'));
    }
  };

  HANDLERS.error = function (state, data) {
    state.errorMsg = data.error;
    if (state.retryCount) window.resetRetryFeedback();
  };

  // The server is transparently retrying a failed provider request; one live
  // toast is refreshed (not stacked) across attempts by its stable id.
  HANDLERS.retry = function (state, data) {
    state.retryCount++;
    _startRetryFeedback(data);
  };

  window.dispatchStreamEvent = function (state, json) {
    var handler = HANDLERS[json.type];
    if (!handler) {
      console.warn('[stream] unknown SSE event type:', json.type, json);
      return;
    }
    handler(state, json);
  };

  window.finalizeStreamRender = function (state) {
    // Retry feedback must never outlive the run (a truncated stream never
    // dispatches `done`, so this is the only cleanup point).
    window.resetRetryFeedback();
    // Cancel a pending frame and render everything left dirty right now —
    // the DOM must be complete before the post-stream server refresh.
    if (_rafId !== null) {
      cancelAnimationFrame(_rafId);
      _rafId = null;
    }
    for (var si = 0; si < state.segments.length; si++) {
      var seg = state.segments[si];
      if (seg.type === 'text' && seg.dirty) {
        window.preserveOpenStates(seg.el, function () { return window.renderMessage(seg.content); });
        seg.dirty = false;
      }
    }
    if (window._updateReasoningButton) {
      var firstText = null;
      for (var sj = 0; sj < state.segments.length; sj++) {
        if (state.segments[sj].type === 'text') { firstText = state.segments[sj].el; break; }
      }
      window._updateReasoningButton(firstText || state.asstDiv);
    }
    // Generation is over: the spinner must not depend on the post-stream refresh
    // finding this node (it does not, if the row has nothing stored).
    var spinner = state.asstDiv.querySelector('.message-spinner');
    if (spinner) spinner.remove();
    window.bindAssistantIdentity(state);
  };
})();
