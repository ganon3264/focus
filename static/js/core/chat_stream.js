(function () {
  function dbg() {
    if (window.DEBUG) console.log('[stream]', Array.prototype.slice.call(arguments));
  }

  var currentController = null;
  var sendBtn = document.getElementById('send-btn');
  var stopBtn = document.getElementById('stop-btn');
  var input = document.getElementById('chat-input');
  var messageList = document.getElementById('message-list');

  if (!sendBtn || !input || !messageList) return;

  /* ── Tool call rendering ── */

  window._renderToolCalls = function (container, calls) {
    var section = container.querySelector('.tool-calls-stream');
    if (!section) {
      section = document.createElement('div');
      section.className = 'tool-calls-stream pl-stream';
      var bodyEl = container.querySelector('.message-body') || container;
      var contentEl = container.querySelector('.message-content');
      if (contentEl && contentEl.parentNode) {
        contentEl.parentNode.insertBefore(section, contentEl.nextSibling);
      } else {
        bodyEl.appendChild(section);
      }
    }
    calls.forEach(function (call) {
      var existing = section.querySelector('[data-call-id="' + call.id + '"]');
      if (existing) return;
      section.appendChild(window.buildToolCallCard(call));
    });
  };

  window._updateToolResult = function (container, callId, name, result, isError) {
    var section = container.querySelector('.tool-calls-stream');
    if (!section) return;
    var card = section.querySelector('[data-call-id="' + callId + '"]');
    if (!card) return;
    var label = card.querySelector('.executing-label');
    if (label) {
      label.textContent = isError ? '(error)' : '(done)';
      label.style.color = isError ? 'var(--danger)' : 'var(--accent)';
    }
    var body = card.querySelector('.tool-result-body');
    if (body) {
      body.style.display = 'block';
      var pre = body.querySelector('pre');
      if (pre) {
        pre.textContent = isError ? '(error) ' + result : result;
        pre.style.color = isError ? 'var(--danger)' : '';
      }
    }
  };

  /* ── UI state helpers ── */

  function _setGeneratingUI(generating) {
    if (generating) {
      sendBtn.classList.add('hidden');
      stopBtn.classList.remove('hidden');
      var fu = document.getElementById('file-upload');
      if (fu) fu.disabled = true;
    } else {
      window._generating = false;
      window._streamingMessageId = null;
      currentController = null;
      sendBtn.classList.remove('hidden');
      stopBtn.classList.add('hidden');
      var fu = document.getElementById('file-upload');
      if (fu) fu.disabled = false;
    }
  }

  function _clearStaleContent(asstDiv, continueText, continueReasoning) {
    if (!asstDiv) return;
    var staleCalls = asstDiv.querySelector('.tool-calls-stream');
    if (staleCalls) staleCalls.remove();
    var staleSection = asstDiv.querySelector('.tool-calls-section');
    if (staleSection) staleSection.remove();

    if (!continueText && !continueReasoning) {
      var contentDivs = asstDiv.querySelectorAll('.message-content');
      for (var j = 0; j < contentDivs.length; j++) {
        contentDivs[j].innerHTML = j === 0 ? '<div class="message-spinner"></div>' : '';
      }
      var reasoningBtn = asstDiv.querySelector('.reasoning-toggle-btn');
      if (reasoningBtn) reasoningBtn.classList.add('hidden');
      asstDiv.classList.remove('reasoning-open');
      var staleBlocks = asstDiv.querySelectorAll('.reasoning-block');
      for (var k = 0; k < staleBlocks.length; k++) staleBlocks[k].remove();
    } else {
      var contentDiv = asstDiv.querySelector('.message-content');
      var pulse = document.createElement('span');
      pulse.className = 'gen-pulse';
      contentDiv.appendChild(pulse);
    }
  }

  /* ── Attachment upload ── */

  async function _uploadAttachments(chatId, isRegen) {
    if (isRegen || !window.stagedFiles || window.stagedFiles.length === 0) return [];
    var filesToUpload = Array.prototype.slice.call(window.stagedFiles);
    var formData = new FormData();
    filesToUpload.forEach(function (f) { formData.append('files', f); });
    try {
      var res = await fetch(window.api.chatAttachments(chatId), { method: 'POST', body: formData });
      if (res.ok) {
        var data = await res.json();
        dbg('Uploaded %d attachments, ids=%o', data.attachments.length, data.attachments);
        if (window.clearUploadedFiles) window.clearUploadedFiles(filesToUpload);
        return data.attachments.map(function (a) { return a.id; });
      }
      console.error('[stream] Upload failed with status', res.status);
    } catch (e) {
      console.error('[stream] Upload failed', e);
    }
    if (window.clearUploadedFiles) window.clearUploadedFiles(filesToUpload);
    return [];
  }

  /* ── Non-stream response handler ── */

  async function _handleNonStream(json, state) {
    state.fullText = json.full_text || '';
    state.fullReasoning = json.full_reasoning || '';
    state.messageId = json.message_id;
    state.userMessageId = json.user_message_id;

    if (state.userMessageId && !state.isRegen) {
      var tempUserMsg = document.getElementById('temp-user-msg');
      if (tempUserMsg) {
        tempUserMsg.id = 'message-' + state.userMessageId;
        tempUserMsg.dataset.messageId = state.userMessageId;
      }
    }

    if (!state.asstDiv) {
      var dataList = document.getElementById('message-list-data');
      state.asstDiv = window.buildAssistantSkeleton(
        dataList ? dataList.getAttribute('data-char-name') : 'Assistant',
        dataList ? dataList.getAttribute('data-char-image') : '',
      );
      state.asstDiv.id = 'streaming-message';
      messageList.insertBefore(state.asstDiv, window.scrollSentinel);
    }

    var contentDiv = state.asstDiv.querySelector('.message-content');
    if (contentDiv) {
      contentDiv.innerHTML = window.renderMessage(state.fullText, 0, state.fullReasoning);
      if (window._updateReasoningButton) window._updateReasoningButton(contentDiv);
    }
    if (state.messageId) {
      state.asstDiv.id = 'message-' + state.messageId;
      state.asstDiv.dataset.messageId = state.messageId;
      window._streamingMessageId = state.messageId;
    }
    await window.refreshMessagesAfterStream(state.chatId, state.userMessageId, state.messageId);
    window._streamingMessageId = null;
  }

  /* ── Stream error handler ── */

  async function _handleStreamError(err, state) {
    console.error('[stream] Error: name=%s, message=%s, fullText.length=%d, messageId=%s',
      err.name, err.message, state.fullText.length, state.messageId);

    if (err.name !== 'AbortError') {
      window.showErrorToast(err.message);
      if (state.asstDiv && state.asstDiv.parentNode) state.asstDiv.remove();
      htmx.ajax('GET', window.api.partials.messageList(state.chatId), {
        target: '#message-list',
        swap: 'innerHTML',
      });
    } else if (!state.fullText) {
      if (state.isRegen) {
        htmx.ajax('GET', window.api.partials.messageList(state.chatId), {
          target: '#message-list',
          swap: 'innerHTML',
        });
      } else if (state.asstDiv && state.asstDiv.parentNode) {
        state.asstDiv.remove();
      }
    } else if (state.messageId) {
      var partialText = state.fullText;
      state.asstDiv.id = 'message-' + state.messageId;
      state.asstDiv.dataset.messageId = state.messageId;
      await window.refreshMessagesAfterStream(state.chatId, state.userMessageId, state.messageId);
      if (partialText) {
        var restoredDiv = document.getElementById('message-' + state.messageId);
        if (restoredDiv) {
          restoredDiv.dataset.rawContent = partialText;
          var restoredContent = restoredDiv.querySelector('.message-content');
          if (restoredContent) {
            restoredContent.innerHTML = window.renderMessage(partialText, 0, state.fullReasoning);
            if (window._updateReasoningButton) window._updateReasoningButton(restoredContent);
          }
        }
      }
    }
  }

  /* ── Main generation orchestrator ── */

  window.triggerGeneration = async function (chatId, asstDiv, isRegen, continueText, continueReasoning) {
    if (window._generating) return;
    window._generating = true;

    var providerId = sendBtn.dataset.providerId;
    if (!providerId) {
      alert('No provider configured. Add one in Providers.');
      window._generating = false;
      return;
    }

    window.hideErrorToast();

    if (currentController) {
      currentController.abort();
      currentController = null;
    }

    _setGeneratingUI(true);
    _clearStaleContent(asstDiv, continueText, continueReasoning);

    var state = new window.StreamState(chatId, asstDiv, isRegen, continueText, continueReasoning);
    currentController = state.controller;
    var signal = state.controller.signal;

    state.fullText = '';
    state.fullReasoning = '';

    var attachmentIds = [];

    try {
      attachmentIds = await _uploadAttachments(chatId, isRegen);

      dbg('Request body: user_message=%s, regenerate=%s, attachment_ids=%o, stagedFiles=%d',
        window._tempUserMessage || '', isRegen, attachmentIds, window.stagedFiles ? window.stagedFiles.length : 0);

      var body = {
        chat_id: chatId,
        provider_id: providerId,
        user_message: window._tempUserMessage || '',
        samplers: window.getActiveSamplers ? window.getActiveSamplers() : {},
        regenerate: isRegen,
        attachment_ids: attachmentIds,
        tools_enabled: window._toolConfig ? window._toolConfig.enabled : false,
        tool_read_only: window._toolConfig ? window._toolConfig.read_only : true,
      };
      if (continueText || continueReasoning) {
        body.continue_text = continueText || '';
        body.continue_reasoning = continueReasoning;
      }

      window._tempUserMessage = '';

      var useStream = body.samplers.stream_enabled !== false;

      var res = await fetch(window.api.stream, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: signal,
      });

      if (!res.ok) {
        var errText = await res.text();
        throw new Error(errText || 'Stream request failed');
      }

      if (!useStream) {
        var json = await res.json();
        await _handleNonStream(json, state);
        _setGeneratingUI(false);
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
        }
      }

      window.finalizeStreamRender(state);

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
      await _handleStreamError(err, state);
    } finally {
      _setGeneratingUI(false);
    }
  };

  /* ── Send button ── */

  sendBtn.addEventListener('click', async function () {
    var chatId = sendBtn.dataset.chatId;
    var providerId = sendBtn.dataset.providerId;

    if (sendBtn.dataset.mode === 'regen') {
      if (!providerId) {
        alert('No provider configured. Add one in Providers.');
        return;
      }
      var dataList = document.getElementById('message-list-data');
      var charName = dataList ? dataList.getAttribute('data-char-name') : 'Assistant';
      var charImagePath = dataList ? dataList.getAttribute('data-char-image') : '';
      var asstDiv = window.buildAssistantSkeleton(charName, charImagePath);
      messageList.insertBefore(asstDiv, window.scrollSentinel);
      asstDiv.scrollIntoView({ behavior: 'smooth' });
      window.triggerGeneration(chatId, asstDiv, false);
      return;
    }

    var text = input.value.trim();
    if (!text && (!window.stagedFiles || window.stagedFiles.length === 0)) return;
    if (!providerId) {
      alert('No provider configured. Add one in Providers.');
      return;
    }

    var existingTemp = document.getElementById('temp-user-msg');
    if (existingTemp) existingTemp.remove();

    var dataList = document.getElementById('message-list-data');
    var personaName = dataList ? dataList.getAttribute('data-persona-name') || 'You' : 'You';
    var personaAvatar = dataList ? dataList.getAttribute('data-persona-avatar') : '';
    var charName = dataList ? dataList.getAttribute('data-char-name') : 'Assistant';
    var charImagePath = dataList ? dataList.getAttribute('data-char-image') : '';

    var userDiv = window.buildUserMessageDiv(text, personaName, personaAvatar, window.stagedFiles);
    messageList.insertBefore(userDiv, window.scrollSentinel);

    var asstDiv = window.buildAssistantSkeleton(charName, charImagePath);
    messageList.insertBefore(asstDiv, window.scrollSentinel);
    asstDiv.scrollIntoView({ behavior: 'smooth' });

    window._tempUserMessage = text;
    input.value = '';
    if (window.resizeTextarea) window.resizeTextarea(input);

    window.triggerGeneration(chatId, asstDiv, false);
  });

  /* ── Stop button ── */

  stopBtn.addEventListener('click', function () {
    if (currentController) {
      currentController.abort();
      currentController = null;
    }
  });

  /* ── Branch ── */

  window.branchFromMessage = async function (messageId, chatId) {
    try {
      var r = await fetch(window.api.chatBranch(chatId, messageId), { method: 'POST' });
      if (!r.ok) throw new Error('Branch failed');
      var d = await r.json();
      window.location.href = '/chat/' + d.id;
    } catch (e) {
      alert(e.message);
    }
  };

  /* ── Post-swap processing ── */

  window._postSwapProcess = function (container) {
    if (!container) return;
    container.querySelectorAll('.markdown-content:not(.processed)').forEach(function (el) {
      el.innerHTML = window.renderMessage(el.textContent || '');
      el.classList.add('processed');
    });
    if (window.syncReasoningButtons) window.syncReasoningButtons(container);
    if (typeof updateSendButtonState === 'function') updateSendButtonState();
    if (typeof updateContinueButtons === 'function') updateContinueButtons();
    window.ensureSentinelAndObserver();
  };

  /* ── Init ── */

  document.addEventListener('DOMContentLoaded', function () {
    var els = document.querySelectorAll('.markdown-content');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      var raw = el.textContent || '';
      el.innerHTML = window.renderMessage(raw);
      el.classList.add('processed');
    }
    if (window.syncReasoningButtons) window.syncReasoningButtons(document);

    var ml = document.getElementById('message-list');
    if (ml) ml.classList.add('ready');

    var savedProvider = StateManager.get('provider_id');
    if (savedProvider) {
      sendBtn.dataset.providerId = savedProvider;
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (evt.detail.target.id === 'message-list') {
      window._postSwapProcess(evt.detail.target);
    }
  });
})();
