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
    this.segments = [];
    this.controller = new AbortController();
  };

  var HANDLERS = {};

  HANDLERS.start = function (state, data) {
    state.messageId = data.message_id;
    window._streamingMessageId = data.message_id;
    state.userMessageId = data.user_message_id;

    dbg('SSE start: message_id=%s, user_message_id=%s', data.message_id, data.user_message_id);

    if (state.userMessageId && !state.isRegen) {
      var tempUserMsg = document.getElementById('temp-user-msg');
      if (tempUserMsg) {
        tempUserMsg.id = 'message-' + state.userMessageId;
        tempUserMsg.dataset.messageId = state.userMessageId;
      }
    }
  };

  HANDLERS.tool_calls = function (state, data) {
    var el = window.segmentBuilders.tool_calls(data.calls);
    _appendSegment(state, 'tool_calls', el);
  };

  HANDLERS.tool_result = function (state, data) {
    var last = _lastSegment(state);
    if (!last || last.type !== 'tool_calls') return;
    window.updateToolCallCard(last.el, data.call_id, data.result, data.is_error);
  };

  HANDLERS.reasoning = function (state, data) {
    var seg = _findOrCreateSegment(state, 'reasoning', function () {
      var idx = 0;
      for (var i = 0; i < state.segments.length; i++) {
        if (state.segments[i].type === 'reasoning') idx++;
      }
      return window.segmentBuilders.reasoning(idx);
    });
    seg.text = (seg.text || '') + (data.text || '');
    var rc = seg.el.querySelector('.reasoning-content');
    if (rc) rc.textContent = seg.text;
    if (window._updateReasoningButton) window._updateReasoningButton(state.asstDiv);
  };

  HANDLERS.token = function (state, data) {
    state.fullText += data.token;
    var seg = _findOrCreateSegment(state, 'text', function () {
      return window.segmentBuilders.text();
    });
    seg.content = (seg.content || '') + data.token;
    window.preserveOpenStates(seg.el, function () { return window.renderMessage(seg.content); });
    if (window._updateReasoningButton) window._updateReasoningButton(seg.el);
    if (window.autoScroll && window.scrollSentinel) {
      window.scrollSentinel.scrollIntoView({ behavior: 'smooth' });
    }
  };

  HANDLERS.done = function (state, data) {
    state.messageId = data.message_id;
    dbg('SSE done: message_id=%s', data.message_id);
  };

  HANDLERS.error = function (state, data) {
    throw new Error(data.error);
  };

  window.dispatchStreamEvent = function (state, json) {
    if (json.type === 'tool_calls') { HANDLERS.tool_calls(state, json); return; }
    if (json.type === 'tool_result') { HANDLERS.tool_result(state, json); return; }
    if (json.type === 'reasoning') { HANDLERS.reasoning(state, json); return; }
    if (json.type === 'start') { HANDLERS.start(state, json); return; }
    if (json.done) { HANDLERS.done(state, json); return; }
    if (json.error) { HANDLERS.error(state, json); return; }
    if (json.token !== undefined) { HANDLERS.token(state, json); return; }
  };

  window.finalizeStreamRender = function (state) {
    for (var si = 0; si < state.segments.length; si++) {
      var seg = state.segments[si];
      if (seg.type === 'text') {
        window.preserveOpenStates(seg.el, function () { return window.renderMessage(seg.content); });
      }
    }
    if (window._updateReasoningButton) {
      var firstText = null;
      for (var si = 0; si < state.segments.length; si++) {
        if (state.segments[si].type === 'text') { firstText = state.segments[si].el; break; }
      }
      window._updateReasoningButton(firstText || state.asstDiv);
    }
    if (state.messageId) {
      state.asstDiv.id = 'message-' + state.messageId;
      state.asstDiv.dataset.messageId = state.messageId;
    }
  };
})();
