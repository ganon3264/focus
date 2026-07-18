(function () {
  var dbg = function () {};
  if (window.DEBUG) {
    dbg = function () { console.log('[stream]', Array.prototype.slice.call(arguments)); };
  }

  /* ── StreamState: mutable state container for one generation ── */

  window.StreamState = function (chatId, asstDiv, isRegen, continueText, continueReasoning) {
    this.chatId = chatId;
    this.asstDiv = asstDiv;
    this.isRegen = isRegen;
    this.continueText = continueText || null;
    this.continueReasoning = continueReasoning || null;
    this.fullText = '';
    this.fullReasoning = '';
    this.messageId = null;
    this.userMessageId = null;
    this.textSegments = [];
    this.currentTextDiv = null;
    this.controller = new AbortController();
  };

  /* ── Event handlers ── */

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
    window._renderToolCalls(state.asstDiv, data.calls);
    var toolSection = state.asstDiv.querySelector('.tool-calls-stream');
    var contDiv = document.createElement('div');
    contDiv.className = 'message-content markdown-content processed pl-stream';
    toolSection.parentNode.insertBefore(contDiv, toolSection.nextSibling);
    state.currentTextDiv = contDiv;
    state.textSegments.push({ div: contDiv, text: '' });
  };

  HANDLERS.tool_result = function (state, data) {
    window._updateToolResult(state.asstDiv, data.call_id, data.name, data.result, data.is_error);
  };

  HANDLERS.reasoning = function (state, data) {
    state.fullReasoning += data.text || '';
    var asstDiv = state.asstDiv;
    var rb = asstDiv.querySelector('.reasoning-block');
    if (!rb) {
      rb = window.buildReasoningBlock();
      var bodyEl = asstDiv.querySelector('.message-body');
      var contentEl = asstDiv.querySelector('.message-content');
      if (bodyEl && contentEl) bodyEl.insertBefore(rb, contentEl);
      else if (bodyEl) bodyEl.appendChild(rb);
    }
    var rc = rb.querySelector('.reasoning-content');
    if (rc) rc.textContent = state.fullReasoning;
    if (window._updateReasoningButton) window._updateReasoningButton(contentEl || asstDiv);
  };

  HANDLERS.token = function (state, data) {
    state.fullText += data.token;
    if (!state.currentTextDiv) {
      state.currentTextDiv = state.asstDiv.querySelector('.message-content');
      if (!state.currentTextDiv) {
        state.currentTextDiv = document.createElement('div');
        state.currentTextDiv.className = 'message-content markdown-content processed pl-stream';
        var bodyEl = state.asstDiv.querySelector('.message-body');
        if (bodyEl) bodyEl.appendChild(state.currentTextDiv);
      }
      state.textSegments.push({ div: state.currentTextDiv, text: '' });
    }
    var seg = state.textSegments[state.textSegments.length - 1];
    seg.text += data.token;
    window.preserveOpenStates(state.currentTextDiv, function () { return window.renderMessage(seg.text); });
    if (window._updateReasoningButton) window._updateReasoningButton(state.currentTextDiv);
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

  /* ── Dispatch: route a parsed SSE event to the correct handler ── */

  window.dispatchStreamEvent = function (state, json) {
    if (json.type === 'tool_calls') { HANDLERS.tool_calls(state, json); return; }
    if (json.type === 'tool_result') { HANDLERS.tool_result(state, json); return; }
    if (json.type === 'reasoning') { HANDLERS.reasoning(state, json); return; }
    if (json.type === 'start') { HANDLERS.start(state, json); return; }
    if (json.done) { HANDLERS.done(state, json); return; }
    if (json.error) { HANDLERS.error(state, json); return; }
    if (json.token !== undefined) { HANDLERS.token(state, json); return; }
  };

  /* ── Post-stream finalization (used after stream completes) ── */

  window.finalizeStreamRender = function (state) {
    if (state.textSegments.length > 0) {
      for (var si = 0; si < state.textSegments.length; si++) {
        var seg = state.textSegments[si];
        var segReasoning = si === 0 ? state.fullReasoning : null;
        window.preserveOpenStates(seg.div, function () { return window.renderMessage(seg.text, 0, segReasoning); });
      }
      if (window._updateReasoningButton) window._updateReasoningButton(state.asstDiv.querySelector('.message-content'));
    }
    if (state.messageId) {
      state.asstDiv.id = 'message-' + state.messageId;
      state.asstDiv.dataset.messageId = state.messageId;
    }
  };
})();
