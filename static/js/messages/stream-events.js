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
    this.segments = [];
    this.controller = new AbortController();
  };

  // ── Identity adoption (shared by stream and non-stream paths) ──

  window.adoptUserMessageId = function (state) {
    if (!state.userMessageId || state.isRegen) return;
    var tempUserMsg = document.getElementById('temp-user-msg');
    if (tempUserMsg) {
      tempUserMsg.id = 'message-' + state.userMessageId;
      tempUserMsg.dataset.messageId = state.userMessageId;
    }
  };

  window.bindAssistantIdentity = function (state) {
    if (!state.messageId) return;
    state.asstDiv.id = 'message-' + state.messageId;
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
    dbg('SSE done: message_id=%s', data.message_id);
  };

  HANDLERS.error = function (state, data) {
    state.errorMsg = data.error;
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
    window.bindAssistantIdentity(state);
  };
})();
