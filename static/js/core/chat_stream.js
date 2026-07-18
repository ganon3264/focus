(function () {
  function dbg(...args) { if (window.DEBUG) console.log('[stream]', ...args); }

  let currentController = null;
  const sendBtn = document.getElementById('send-btn');
  const stopBtn = document.getElementById('stop-btn');
  const input = document.getElementById('chat-input');
  const messageList = document.getElementById('message-list');

  if (!sendBtn || !input || !messageList) return;

  function createAssistantSkeleton(charName, charImagePath) {
    const asstDiv = document.createElement('div');
    asstDiv.className = 'message msg';
    asstDiv.id = 'streaming-message';
    const avatarHtml = charImagePath
      ? `<img src="/${charImagePath}" alt="" class="cursor-pointer" onclick="openLightbox(this.src)">`
      : window.escapeHtml((charName || 'A')[0]);
    asstDiv.innerHTML = `
      <div class="message-body">
        <div class="flex items-start gap-3 min-w-0">
          <div class="message-avatar">${avatarHtml}</div>
          <div class="min-w-0">
            <div class="text-sm font-medium" style="color:var(--text)">${window.escapeHtml(charName)}</div>
            <div class="text-xs text-muted flex items-center gap-1.5 flex-wrap mt-0.5">
              <button class="reasoning-toggle-btn hidden" onclick="toggleReasoning(this)" aria-label="Toggle reasoning" style="background:none;border:none;padding:0;font:inherit;cursor:pointer;display:inline-flex;align-items:center;gap:0.25rem">
                <svg class="w-3 h-3 reasoning-chevron" style="color:var(--text-faint);transition:transform 0.2s ease" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                <span>Reasoning</span>
              </button>
            </div>
          </div>
        </div>
        <div class="message-content markdown-content processed" style="padding-left:3rem"></div>
      </div>
    `;
    return asstDiv;
  }



  window._renderToolCalls = function (container, calls) {
    var section = container.querySelector('.tool-calls-stream');
    if (!section) {
      section = document.createElement('div');
      section.className = 'tool-calls-stream';
      section.style.cssText = 'padding-left:3rem';
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
      var card = document.createElement('details');
      card.className = 'details tool-call';
      card.setAttribute('data-call-id', call.id);
      card.innerHTML =
        '<summary>' +
        '<svg class="w-3 h-3 chevron" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>' +
        '<code class="font-bold">' + window.escapeHtml(call.name) + '</code>' +
        '<span class="truncate max-w-[300px]">' + window.escapeHtml(JSON.stringify(call.arguments)) + '</span>' +
        '</summary>' +
        '<div class="tool-result-body" style="display:none">' +
        '<pre class="whitespace-pre-wrap break-all"></pre>' +
        '</div>';
      section.appendChild(card);
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

  function _createAttachmentPreview(file) {
    var wrapper = document.createElement('div');
    wrapper.className = 'relative group';

    if (file.type.startsWith('image/')) {
      var img = document.createElement('img');
      img.className = 'h-24 rounded object-cover border border-border cursor-pointer hover:opacity-90 transition-opacity';
      img.src = URL.createObjectURL(file);
      img.alt = 'attachment';
      img.onclick = function () { openLightbox(this.src); };
      wrapper.appendChild(img);
    } else {
      wrapper.className = 'h-16 bg-surface-3 px-3 rounded border border-border flex items-center gap-2 text-sm';
      wrapper.innerHTML = '<span>' + (window.getSvgSprite ? window.getSvgSprite('music', 18) : '') + '</span>';
      var audio = document.createElement('audio');
      audio.controls = true;
      audio.className = 'h-8 max-w-[200px]';
      audio.style.cssText = 'filter: contrast(0.8) grayscale(1)';
      var source = document.createElement('source');
      source.src = URL.createObjectURL(file);
      source.type = file.type;
      audio.appendChild(source);
      wrapper.appendChild(audio);
    }

    return wrapper;
  }

  function createUserMessageDiv(text) {
    const dataList = document.getElementById('message-list-data');
    const personaName = dataList ? dataList.getAttribute('data-persona-name') || 'You' : 'You';
    const personaAvatar = dataList ? dataList.getAttribute('data-persona-avatar') : '';

    const div = document.createElement('div');
    div.className = 'message relative msg';
    div.id = 'temp-user-msg';

    div.innerHTML = [
      '<div class="message-body">',
      '<div class="flex items-start gap-3 min-w-0">',
      '<div class="message-avatar">',
      personaAvatar
        ? '<img src="/' + personaAvatar + '" alt="" class="cursor-pointer" onclick="openLightbox(this.src)">'
        : window.escapeHtml((personaName || 'Y')[0]),
      '</div>',
      '<div class="min-w-0">',
      '<div class="text-sm font-medium" style="color:var(--text)">' + window.escapeHtml(personaName) + '</div>',
      '</div>',
      '</div>',
      '<div class="message-content markdown-content" style="padding-left:3rem"></div>',
      '</div>',
    ].join('');

    var staged = window.stagedFiles;
    if (staged && staged.length > 0) {
      var attContainer = document.createElement('div');
      attContainer.className = 'flex gap-2 flex-wrap mb-2';
      attContainer.style.cssText = 'padding-left:3rem';
      staged.forEach(function (f) { attContainer.appendChild(_createAttachmentPreview(f)); });
      var bodyDiv = div.querySelector('.message-body');
      var contentEl = div.querySelector('.message-content');
      if (bodyDiv && contentEl) bodyDiv.insertBefore(attContainer, contentEl);
    }

    var contentDiv = div.querySelector('.message-content');
    if (contentDiv) {
      contentDiv.innerHTML = window.renderMessage(text);
      contentDiv.classList.add('processed');
    }

    return div;
  }

  window.triggerGeneration = async function (chatId, asstDiv, isRegen = false, continueText = null) {
    let textSegments = [];
    let currentTextDiv = null;

    const providerId = sendBtn.dataset.providerId;
    if (!providerId) {
      alert('No provider configured. Add one in Providers.');
      return;
    }

    window.hideErrorToast();

    if (currentController) {
      currentController.abort();
      currentController = null;
    }

    sendBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');
    const fileUpload = document.getElementById('file-upload');
    if (fileUpload) fileUpload.disabled = true;

    if (asstDiv) {
      textSegments = [];
      currentTextDiv = null;
      var staleCalls = asstDiv.querySelector('.tool-calls-stream');
      if (staleCalls) staleCalls.remove();
      var staleSection = asstDiv.querySelector('.tool-calls-section');
      if (staleSection) staleSection.remove();
      if (!continueText) {
        var contentDivs = asstDiv.querySelectorAll('.message-content');
        for (var j = 0; j < contentDivs.length; j++) {
          contentDivs[j].innerHTML = (j === 0) ? '<div class="message-spinner"></div>' : '';
        }
        const reasoningBtn = asstDiv.querySelector('.reasoning-toggle-btn');
        if (reasoningBtn) reasoningBtn.classList.add('hidden');
        asstDiv.classList.remove('reasoning-open');
        var staleBlocks = asstDiv.querySelectorAll('.reasoning-block');
        for (var k = 0; k < staleBlocks.length; k++) staleBlocks[k].remove();
      } else {
        const contentDiv = asstDiv.querySelector('.message-content');
        if (contentDiv) {
          const pulse = document.createElement('span');
          pulse.className = 'gen-pulse';
          contentDiv.appendChild(pulse);
        }
      }
    }

    currentController = new AbortController();
    const signal = currentController.signal;

    let attachmentIds = [];
    if (!isRegen && window.stagedFiles && window.stagedFiles.length > 0) {
      const filesToUpload = [...window.stagedFiles];
      const formData = new FormData();
      filesToUpload.forEach((f) => formData.append('files', f));
      try {
        const uploadRes = await fetch(window.api.chatAttachments(chatId), {
          method: 'POST',
          body: formData,
        });
        if (uploadRes.ok) {
          const data = await uploadRes.json();
          attachmentIds = data.attachments.map((a) => a.id);
          dbg('Uploaded %d attachments, ids=%o', attachmentIds.length, attachmentIds);
        } else {
          console.error('[stream] Upload failed with status', uploadRes.status);
        }
      } catch (e) {
        console.error('[stream] Upload failed', e);
      }
      if (window.clearUploadedFiles) window.clearUploadedFiles(filesToUpload);
    }

    dbg('Request body: user_message=%s, regenerate=%s, attachment_ids=%o, stagedFiles=%d',
      window._tempUserMessage || '', isRegen, attachmentIds, window.stagedFiles ? window.stagedFiles.length : 0);

    const body = {
      chat_id: chatId,
      provider_id: providerId,
      user_message: window._tempUserMessage || '',
      samplers: window.getActiveSamplers ? window.getActiveSamplers() : {},
      regenerate: isRegen,
      attachment_ids: attachmentIds,
      tools_enabled: window._toolConfig ? window._toolConfig.enabled : false,
      tool_read_only: window._toolConfig ? window._toolConfig.read_only : true,
    };
    if (continueText) body.continue_text = continueText;

    window._tempUserMessage = '';

    const useStream = body.samplers.stream_enabled !== false;

    let fullText = '';

    try {
      const res = await fetch(window.api.stream, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal,
      });

      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || 'Stream request failed');
      }

      if (!useStream) {
        const json = await res.json();
        fullText = json.full_text || '';
        const messageId = json.message_id;
        const userMessageId = json.user_message_id;

        if (userMessageId && !isRegen) {
          const tempUserMsg = document.getElementById('temp-user-msg');
          if (tempUserMsg) {
            tempUserMsg.id = 'message-' + userMessageId;
            tempUserMsg.dataset.messageId = userMessageId;
          }
        }

        if (!asstDiv) {
          const dataList = document.getElementById('message-list-data');
          asstDiv = createAssistantSkeleton(
            dataList ? dataList.getAttribute('data-char-name') : 'Assistant',
            dataList ? dataList.getAttribute('data-char-image') : '',
          );
          asstDiv.id = 'streaming-message';
          messageList.insertBefore(asstDiv, window.scrollSentinel);
        }

        const contentDiv = asstDiv.querySelector('.message-content');
        if (contentDiv) {
          contentDiv.innerHTML = window.renderMessage(fullText);
          if (window._updateReasoningButton) window._updateReasoningButton(contentDiv);
        }
        if (messageId) {
          asstDiv.id = 'message-' + messageId;
          asstDiv.dataset.messageId = messageId;
          window._streamingMessageId = messageId;
        }
        await window.refreshMessagesAfterStream(chatId, userMessageId, messageId);
        window._streamingMessageId = null;
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let messageId = null;
      let userMessageId = null;
      let prefillMode = false;
      fullText = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if (!data) continue;
          let json;
          try {
            json = JSON.parse(data);
          } catch (e) {
            continue;
          }
          if (json.type === 'start') {
            messageId = json.message_id;
            window._streamingMessageId = messageId;
            userMessageId = json.user_message_id;
            prefillMode = json.prefill_mode || false;

            dbg('SSE start: message_id=%s, user_message_id=%s, prefill=%s',
              messageId, userMessageId, prefillMode);

            if (userMessageId && !isRegen) {
              const tempUserMsg = document.getElementById('temp-user-msg');
              if (tempUserMsg) {
                tempUserMsg.id = 'message-' + userMessageId;
                tempUserMsg.dataset.messageId = userMessageId;
              }
            }
          } else if (json.type === 'tool_calls') {
            window._renderToolCalls(asstDiv, json.calls);
            var toolSection = asstDiv.querySelector('.tool-calls-stream');
            var contDiv = document.createElement('div');
            contDiv.className = 'message-content markdown-content processed';
            contDiv.style.cssText = 'padding-left:3rem';
            toolSection.parentNode.insertBefore(contDiv, toolSection.nextSibling);
            currentTextDiv = contDiv;
            textSegments.push({ div: contDiv, text: '' });
          } else if (json.type === 'tool_result') {
            window._updateToolResult(asstDiv, json.call_id, json.name, json.result, json.is_error);
          } else if (json.token !== undefined) {
            fullText += json.token;
            if (!currentTextDiv) {
              currentTextDiv = asstDiv.querySelector('.message-content');
              textSegments.push({ div: currentTextDiv, text: '' });
            }
            var seg = textSegments[textSegments.length - 1];
            seg.text += json.token;
            var startIdx = 0;
            for (var si = 0; si < textSegments.length - 1; si++) {
              startIdx += window.extractThoughtsSafely(textSegments[si].text).thoughts.length;
            }
            let displayText = seg.text;
            if (continueText && prefillMode && textSegments.length === 1) {
              displayText = continueText + seg.text;
            }
            window.preserveOpenStates(currentTextDiv, () => window.renderMessage(displayText, startIdx));
            if (window._updateReasoningButton) window._updateReasoningButton(currentTextDiv);
            if (window.autoScroll && window.scrollSentinel) {
              window.scrollSentinel.scrollIntoView({ behavior: 'smooth' });
            }
          } else if (json.error) {
            throw new Error(json.error);
          } else if (json.done) {
            messageId = json.message_id;
            dbg('SSE done: message_id=%s', messageId);
          }
        }
      }

      if (textSegments.length > 0) {
        var finalStartIdx = 0;
        for (var si = 0; si < textSegments.length; si++) {
          var seg = textSegments[si];
          let segDisplayText = seg.text;
          if (continueText && prefillMode && si === 0) {
            segDisplayText = continueText + seg.text;
          }
          window.preserveOpenStates(seg.div, () => window.renderMessage(segDisplayText, finalStartIdx));
          finalStartIdx += window.extractThoughtsSafely(seg.text).thoughts.length;
        }
        if (window._updateReasoningButton) window._updateReasoningButton(asstDiv.querySelector('.message-content'));
      }
      if (messageId) {
        asstDiv.id = 'message-' + messageId;
        asstDiv.dataset.messageId = messageId;
      }

      dbg('Refreshing messages: chatId=%s, userMsgId=%s, asstMsgId=%s',
        chatId, userMessageId, messageId);
      await window.refreshMessagesAfterStream(chatId, userMessageId, messageId);

      if (window.updateClaudeCache && window.APP_PROVIDERS) {
        const doneProvider = window.APP_PROVIDERS.find(function (p) { return p.id === providerId; });
        if (window.isClaudeProvider(doneProvider)) {
          window.updateClaudeCache(providerId, body.samplers);
        }
      }
    } catch (err) {
      console.error('[stream] Error: name=%s, message=%s, fullText.length=%d, messageId=%s',
        err.name, err.message, fullText.length, messageId);
      if (err.name !== 'AbortError') {
        window.showErrorToast(err.message);
        if (asstDiv && asstDiv.parentNode) asstDiv.remove();
        htmx.ajax('GET', window.api.partials.messageList(chatId), {
          target: '#message-list',
          swap: 'innerHTML',
        });
      } else if (!fullText) {
        if (isRegen) {
          htmx.ajax('GET', window.api.partials.messageList(chatId), {
            target: '#message-list',
            swap: 'innerHTML',
          });
        } else if (asstDiv && asstDiv.parentNode) {
          asstDiv.remove();
        }
      } else if (messageId) {
        const partialText = fullText;
        asstDiv.id = 'message-' + messageId;
        asstDiv.dataset.messageId = messageId;
        await window.refreshMessagesAfterStream(chatId, userMessageId, messageId);
        if (partialText) {
          const restoredDiv = document.getElementById('message-' + messageId);
          if (restoredDiv) {
            restoredDiv.dataset.rawContent = partialText;
            const restoredContent = restoredDiv.querySelector('.message-content');
            if (restoredContent) {
              restoredContent.innerHTML = window.renderMessage(partialText);
              if (window._updateReasoningButton) window._updateReasoningButton(restoredContent);
            }
          }
        }
      }
    } finally {
      window._streamingMessageId = null;
      currentController = null;
      sendBtn.classList.remove('hidden');
      stopBtn.classList.add('hidden');
      const fileUpload = document.getElementById('file-upload');
      if (fileUpload) fileUpload.disabled = false;
    }
  };

  sendBtn.addEventListener('click', async function () {
    const chatId = sendBtn.dataset.chatId;
    const providerId = sendBtn.dataset.providerId;

    if (sendBtn.dataset.mode === 'regen') {
      if (!providerId) {
        alert('No provider configured. Add one in Providers.');
        return;
      }

      const dataList = document.getElementById('message-list-data');
      const charName = dataList ? dataList.getAttribute('data-char-name') : 'Assistant';
      const charImagePath = dataList ? dataList.getAttribute('data-char-image') : '';

      const asstDiv = createAssistantSkeleton(charName, charImagePath);
      messageList.insertBefore(asstDiv, window.scrollSentinel);
      asstDiv.scrollIntoView({ behavior: 'smooth' });

      window.triggerGeneration(chatId, asstDiv, true);
      return;
    }

    const text = input.value.trim();
    if (!text && (!window.stagedFiles || window.stagedFiles.length === 0)) return;
    if (!providerId) {
      alert('No provider configured. Add one in Providers.');
      return;
    }

    const existingTemp = document.getElementById('temp-user-msg');
    if (existingTemp) existingTemp.remove();

    const userDiv = createUserMessageDiv(text);
    messageList.insertBefore(userDiv, window.scrollSentinel);

    const dataList = document.getElementById('message-list-data');
    const charName = dataList ? dataList.getAttribute('data-char-name') : 'Assistant';
    const charImagePath = dataList ? dataList.getAttribute('data-char-image') : '';
    const asstDiv = createAssistantSkeleton(charName, charImagePath);
    messageList.insertBefore(asstDiv, window.scrollSentinel);
    asstDiv.scrollIntoView({ behavior: 'smooth' });

    window._tempUserMessage = text;

    input.value = '';
    if (window.resizeTextarea) window.resizeTextarea(input);

    window.triggerGeneration(chatId, asstDiv, false);
  });

  stopBtn.addEventListener('click', function () {
    if (currentController) {
      currentController.abort();
      currentController = null;
    }
  });

  window.branchFromMessage = async function (messageId, chatId) {
    try {
      const r = await fetch(window.api.chatBranch(chatId, messageId), { method: 'POST' });
      if (!r.ok) throw new Error('Branch failed');
      const d = await r.json();
      window.location.href = '/chat/' + d.id;
    } catch (e) {
      alert(e.message);
    }
  };

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

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.markdown-content').forEach(function (el) {
      const raw = el.textContent || '';
      el.innerHTML = window.renderMessage(raw);
      el.classList.add('processed');
    });
    if (window.syncReasoningButtons) window.syncReasoningButtons(document);

    document.getElementById('message-list')?.classList.add('ready');

    const savedProvider = StateManager.get('provider_id');
    if (savedProvider) {
      const sendBtn = document.getElementById('send-btn');
      if (sendBtn) sendBtn.dataset.providerId = savedProvider;
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (evt.detail.target.id === 'message-list') {
      window._postSwapProcess(evt.detail.target);
    }
  });
})();
