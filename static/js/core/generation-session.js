// Single owner of the generation lifecycle: AbortController, active flag,
// streaming message id, and the stop-escalation ladder. UI code talks to it
// via window.Generation — never by poking globals.
(function () {
  function dbg() {
    if (window.DEBUG) console.log('[stream]', Array.prototype.slice.call(arguments));
  }

  // Stop-request escalation: the stop POST gets a hard timeout, and even a
  // successful one only waits this long for the server's `done` before the
  // stream is force-aborted (server-side disconnect cancel saves partials).
  var STOP_POST_TIMEOUT_MS = 4000;
  var STOP_DRAIN_TIMEOUT_MS = 8000;

  var _active = false;
  var _controller = null;
  var _state = null;
  var _pendingStop = null;

  function isActive() { return _active; }

  function streamingId() { return _state ? _state.messageId : null; }

  function clearPendingStop() {
    if (_pendingStop) {
      clearTimeout(_pendingStop.timer);
      _pendingStop = null;
    }
  }

  function abortCurrent() {
    if (_controller) {
      _controller.abort();
      _controller = null;
    }
  }

  function handleFailure(state, message, name) {
    console.error('[stream] Failure: name=%s, message=%s', name, message);
    if (name !== 'AbortError') {
      window.showErrorToast(message);
    }

    // Remove the empty/stale assistant skeleton, then restore the list from
    // the server. Never refresh by message id here — the message may not exist
    // (rolled back on failure), which would otherwise 404.
    if (state.asstDiv && state.asstDiv.parentNode) {
      state.asstDiv.remove();
    }

    if (state.chatId) {
      hxGet(window.api.partials.messageList(state.chatId), {
        target: '#message-list',
        swap: 'innerHTML',
      });
      if (window._refreshChatList) window._refreshChatList(state.chatId);
    }

    if (typeof updateSendButtonState === 'function') updateSendButtonState();
  }

  async function _handleNonStream(json, state) {
    state.fullText = json.full_text || '';
    state.messageId = json.message_id;
    state.userMessageId = json.user_message_id;

    window.adoptUserMessageId(state);

    if (!state.asstDiv) {
      var dataList = document.getElementById('message-list-data');
      state.asstDiv = window.buildAssistantSkeleton(
        dataList ? dataList.getAttribute('data-char-name') : 'Assistant',
        dataList ? dataList.getAttribute('data-char-image') : '',
      );
      state.asstDiv.id = 'streaming-message';
      var messageList = document.getElementById('message-list');
      messageList.insertBefore(state.asstDiv, window.scrollSentinel);
    }

    var bodyEl = state.asstDiv.querySelector('.message-body');
    var contentDiv = bodyEl ? bodyEl.querySelector('.message-content') : null;
    if (!contentDiv) {
      contentDiv = window.segmentBuilders.text();
      if (bodyEl) bodyEl.appendChild(contentDiv);
    }
    contentDiv.innerHTML = window.renderMessage(state.fullText);
    if (window._updateReasoningButton) window._updateReasoningButton(contentDiv);

    window.bindAssistantIdentity(state);
    await window.refreshMessagesAfterStream(state.chatId, state.userMessageId, state.messageId);
  }

  window.Generation = {
    isActive: isActive,
    streamingId: streamingId,

    async begin(chatId, asstDiv, opts) {
      opts = opts || {};
      if (_active) return;
      _active = true;

      var providerId = StateManager.get('provider_id');
      if (!providerId) {
        window.showErrorToast('No provider configured. Add one in Providers.');
        _active = false;
        return;
      }

      window.hideErrorToast();
      abortCurrent();

      setGeneratingUI(true);
      clearStaleContent(asstDiv, opts.continueText, opts.continueReasoning);

      var state = new window.StreamState(chatId, asstDiv, !!opts.isRegen, opts.continueText, opts.continueReasoning);

      // Continue: reuse the existing content block as the first text segment
      // so streamed tokens replace its contents in place instead of spawning a
      // second block below. Content is NOT seeded here — the stream always
      // carries the full text (echoing providers resend the partial; others get
      // it synthesized server-side).
      if (opts.continueText) {
        var bodyEl = asstDiv.querySelector('.message-body');
        var contentDiv = bodyEl ? bodyEl.querySelector('.message-content') : null;
        if (contentDiv) {
          state.segments.push({ type: 'text', el: contentDiv, content: '' });
        }
      }

      _state = state;
      _controller = state.controller;

      try {
        var attachmentIds = await window.uploadStagedAttachments(chatId, opts.isRegen);

        dbg('Request body: user_message=%r, regenerate=%s, attachment_ids=%o',
          opts.userMessage || '', opts.isRegen, attachmentIds);

        var body = {
          chat_id: chatId,
          provider_id: providerId,
          user_message: opts.userMessage || '',
          samplers: window.getActiveSamplers ? window.getActiveSamplers() : {},
          regenerate: !!opts.isRegen,
          attachment_ids: attachmentIds,
          tools_enabled: window._toolConfig ? window._toolConfig.enabled : false,
          tool_read_only: window._toolConfig ? window._toolConfig.read_only : true,
        };
        if (opts.continueText || opts.continueReasoning) {
          body.continue_text = opts.continueText || '';
          body.continue_reasoning = opts.continueReasoning;
        }

        var useStream = body.samplers.stream_enabled !== false;

        var res = await fetch(window.api.stream, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
          signal: state.controller.signal,
        });

        if (!res.ok) {
          var errText = await res.text();
          throw new Error(errText || 'Stream request failed');
        }

        if (!useStream) {
          await _handleNonStream(await res.json(), state);
          return;
        }

        var reader = res.body.getReader();
        var decoder = new TextDecoder();
        var buffer = '';

        while (true) {
          var result = await reader.read();
          if (result.done) break;
          buffer += decoder.decode(result.value, { stream: true });
          var lines = buffer.split('\n');
          buffer = lines.pop();
          for (var i = 0; i < lines.length; i++) {
            var line = lines[i];
            if (!line.startsWith('data: ')) continue;
            var raw = line.slice(6).trim();
            if (!raw) continue;
            var parsed;
            try {
              parsed = JSON.parse(raw);
            } catch (e) {
              continue;
            }
            window.dispatchStreamEvent(state, parsed);
            if (state.errorMsg) break;
          }
          if (state.errorMsg) break;
        }

        if (state.errorMsg) {
          handleFailure(state, state.errorMsg, 'Error');
          return;
        }

        window.finalizeStreamRender(state);

        if (_pendingStop) {
          clearPendingStop();
          window.hideInfoToast();
          window.showSuccessToast('Generation stopped');
        }

        dbg('Refreshing messages: chatId=%s, userMsgId=%s, asstMsgId=%s',
          chatId, state.userMessageId, state.messageId);
        await window.refreshMessagesAfterStream(chatId, state.userMessageId, state.messageId);

        if (window.updateClaudeCache && window.APP_PROVIDERS) {
          var doneProvider = window.APP_PROVIDERS.find(function (p) { return p.id === providerId; });
          if (window.isClaudeProvider(doneProvider)) {
            window.updateClaudeCache(providerId, body.samplers);
          }
        }
      } catch (err) {
        handleFailure(state, err.message, err.name);
      } finally {
        clearPendingStop();
        setGeneratingUI(false);
        _controller = null;
        _state = null;
        _active = false;
      }
    },

    stop() {
      if (!_controller || _pendingStop) return;
      var msgId = streamingId();
      if (!msgId) {
        abortCurrent();
        return;
      }

      window.showInfoToast('Stopping generation…', { duration: 6000 });

      // The stop POST itself must not hang on a flaky connection — give it its
      // own timeout and fall back to a hard abort.
      var postCtl = new AbortController();
      var postTimer = setTimeout(function () { postCtl.abort(); }, STOP_POST_TIMEOUT_MS);
      fetch('/api/stop-generation/' + encodeURIComponent(msgId), {
        method: 'POST',
        signal: postCtl.signal,
      }).catch(function () {
        clearPendingStop();
        abortCurrent();
        window.hideInfoToast();
        window.showSuccessToast('Generation stopped');
      }).finally(function () {
        clearTimeout(postTimer);
      });

      // Watchdog: if the server hasn't confirmed with `done` in time, cut the
      // connection. Starlette cancels the generator on disconnect, so partials
      // still get persisted server-side.
      _pendingStop = { timer: setTimeout(function () {
        _pendingStop = null;
        abortCurrent();
        window.hideInfoToast();
        window.showSuccessToast('Generation stopped');
      }, STOP_DRAIN_TIMEOUT_MS) };
    },
  };

  var stopBtn = document.getElementById('stop-btn');
  if (stopBtn) stopBtn.addEventListener('click', function () { window.Generation.stop(); });
})();
