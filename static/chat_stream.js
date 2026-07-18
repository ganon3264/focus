(function () {
  let currentController = null;
  const sendBtn = document.getElementById('send-btn');
  const stopBtn = document.getElementById('stop-btn');
  const input = document.getElementById('chat-input');
  const messageList = document.getElementById('message-list');

  if (!sendBtn || !input || !messageList) return;

  function _updateReasoningButton(contentDiv) {
    const msg = contentDiv.closest('.message');
    if (!msg) return;
    const btn = msg.querySelector('.reasoning-toggle-btn');
    if (!btn) return;
    const hasReasoning = contentDiv.querySelector('details.reasoning');
    btn.classList.toggle('hidden', !hasReasoning);
  }

  function syncReasoningButtons(container) {
    if (!container) return;
    const root = container === document ? document : container;
    root.querySelectorAll('.message-content').forEach((el) => _updateReasoningButton(el));
  }

  window.syncReasoningButtons = syncReasoningButtons;

  function preserveOpenStates(container, renderFn) {
    const openStates = new Set();
    container.querySelectorAll('details.reasoning[open]').forEach((d) => {
      if (d.dataset.thinkId) openStates.add(d.dataset.thinkId);
    });
    container.innerHTML = renderFn();
    openStates.forEach((id) => {
      const el = container.querySelector(`details.reasoning[data-think-id="${id}"]`);
      if (el) el.setAttribute('open', '');
    });
  }

  function resizeTextarea(el) {
    el.style.height = '44px';
    if (el.value === '') {
      el.style.overflowY = 'hidden';
      return;
    }
    const scrollHeight = el.scrollHeight;
    if (scrollHeight > 44) {
      el.style.height = Math.min(250, scrollHeight) + 'px';
    }
    el.style.overflowY = scrollHeight > 250 ? 'auto' : 'hidden';
  }

  function updateSendButtonState() {
    const text = input.value.trim();
    const dataList = document.getElementById('message-list-data');
    const lastRole = dataList ? dataList.getAttribute('data-last-role') : '';
    const isRegenMode = !text && window.stagedFiles.length === 0 && lastRole === 'user';

    if (isRegenMode) {
      sendBtn.innerHTML = window.getSvgSprite('regen', 18);
      sendBtn.title = 'Regenerate';
      sendBtn.dataset.mode = 'regen';
    } else {
      sendBtn.innerHTML = window.getSvgSprite('send', 18);
      sendBtn.title = 'Send message';
      sendBtn.dataset.mode = 'send';
    }
  }

  input.addEventListener('input', function () {
    resizeTextarea(this);
    updateSendButtonState();
  });

  if (sendBtn) {
    updateSendButtonState();
  }

  function _replaceMessageNode(doc, msgId, inDeleteMode) {
    const newMsg = doc.getElementById('message-' + msgId);
    if (!newMsg) return;

    let oldMsg = document.getElementById('message-' + msgId);
    if (!oldMsg) {
      const ph = document.querySelector('.message-placeholder[data-msg-id="' + msgId + '"]');
      if (ph) oldMsg = ph;
    }

    if (!oldMsg) return;

    newMsg.style.setProperty('animation', 'none', 'important');
    oldMsg.replaceWith(newMsg);
    htmx.process(newMsg);
    newMsg.querySelectorAll('.markdown-content:not(.processed)').forEach(function (el) {
      el.innerHTML = window.renderMessage(el.textContent || '');
      el.classList.add('processed');
    });
    syncReasoningButtons(newMsg);
    if (inDeleteMode) {
      const cb = newMsg.querySelector('.delete-mode-checkbox');
      if (cb) cb.classList.remove('hidden');
      const actions = newMsg.querySelector('.normal-mode-actions');
      if (actions) actions.classList.add('hidden');
    }
    if (window._isMessagePruned && window._isMessagePruned(msgId)) {
      window._unpruneMessage(msgId);
    }
  }

  async function refreshMessagesAfterStream(chatId, userMsgId, asstMsgId) {
    const resp = await fetch(api.partials.messageList(chatId));
    if (!resp.ok) return;
    const html = await resp.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');

    const newSentinel = doc.getElementById('message-list-data');
    const oldSentinel = document.getElementById('message-list-data');
    if (newSentinel && oldSentinel) {
      oldSentinel.replaceWith(newSentinel);
    }

    const toolbar = document.getElementById('delete-toolbar');
    const inDeleteMode = toolbar && !toolbar.classList.contains('hidden');

    const ids = [userMsgId, asstMsgId].filter(Boolean);
    for (const id of ids) {
      _replaceMessageNode(doc, id, inDeleteMode);
    }

    if (typeof updateSendButtonState === 'function') {
      updateSendButtonState();
    }

    window.ensureSentinelAndObserver();
  }

  async function refreshSingleMessage(chatId, messageId) {
    var existingMsg = document.getElementById('message-' + messageId);
    if (!existingMsg) {
      var resp = await fetch(api.partials.messageList(chatId));
      if (!resp.ok) return;
      var html = await resp.text();
      var doc = new DOMParser().parseFromString(html, 'text/html');
      _replaceMessageNode(doc, messageId, document.getElementById('delete-toolbar') && !document.getElementById('delete-toolbar').classList.contains('hidden'));
      window.ensureSentinelAndObserver();
      return;
    }

    var indexEl = existingMsg.querySelector('.meta-right [style*="font-size: 1.75rem"]');
    var msgIndex = indexEl ? parseInt(indexEl.textContent.replace('#', '').trim()) || 1 : 1;
    var msgList = document.getElementById('message-list');
    var isLatest = msgList ? existingMsg === msgList.querySelector('.message:last-of-type') : false;

    var url = '/partials/message/' + chatId + '/' + messageId + '?msg_index=' + msgIndex + '&is_latest=' + isLatest;
    var resp = await fetch(url);
    if (!resp.ok) return;
    var html = await resp.text();
    var doc = new DOMParser().parseFromString(html, 'text/html');

    _replaceMessageNode(doc, messageId, document.getElementById('delete-toolbar') && !document.getElementById('delete-toolbar').classList.contains('hidden'));
    window.ensureSentinelAndObserver();
  }

  window.refreshSingleMessage = refreshSingleMessage;

  window.triggerGeneration = async function (chatId, asstDiv, isRegen = false, continueText = null) {
    const providerId = sendBtn.dataset.providerId;
    if (!providerId) {
      alert('No provider configured. Add one in Providers.');
      return;
    }

    const errorToast = document.getElementById('error-toast');
    if (errorToast) errorToast.classList.add('hidden');

    if (currentController) {
      currentController.abort();
      currentController = null;
    }

    sendBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');
    const fileUpload = document.getElementById('file-upload');
    if (fileUpload) fileUpload.disabled = true;

    if (!continueText) {
      const contentDiv = asstDiv.querySelector('.message-content');
      if (contentDiv) {
        contentDiv.innerHTML = '<div class="message-spinner"></div>';
      }
      const reasoningBtn = asstDiv.querySelector('.reasoning-toggle-btn');
      if (reasoningBtn) reasoningBtn.classList.add('hidden');
    } else {
      const contentDiv = asstDiv.querySelector('.message-content');
      if (contentDiv) {
        const pulse = document.createElement('span');
        pulse.className = 'gen-pulse';
        contentDiv.appendChild(pulse);
      }
    }

    currentController = new AbortController();
    const signal = currentController.signal;

    let attachmentIds = [];
    if (!isRegen && window.stagedFiles.length > 0) {
      const filesToUpload = [...window.stagedFiles];
      const formData = new FormData();
      filesToUpload.forEach((f) => formData.append('files', f));
      try {
        const uploadRes = await fetch(api.chatAttachments(chatId), {
          method: 'POST',
          body: formData,
        });
        if (uploadRes.ok) {
          const data = await uploadRes.json();
          attachmentIds = data.attachments.map((a) => a.id);
        }
      } catch (e) {
        console.error('Upload failed', e);
      }
      window.clearUploadedFiles(filesToUpload);
    }

    const body = {
      chat_id: chatId,
      provider_id: providerId,
      user_message: window._tempUserMessage || '',
      samplers: window.getActiveSamplers ? window.getActiveSamplers() : {},
      regenerate: isRegen,
      attachment_ids: attachmentIds,
    };
    if (continueText) body.continue_text = continueText;

    window._tempUserMessage = '';

    const useStream = body.samplers.stream_enabled !== false;

    let fullText = '';

    try {
      const res = await fetch(api.stream, {
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
        const fullText = json.full_text || '';
        const messageId = json.message_id;
        const userMessageId = json.user_message_id;

        const contentDiv = asstDiv.querySelector('.message-content');
        if (contentDiv) {
          contentDiv.innerHTML = window.renderMessage(fullText);
          _updateReasoningButton(contentDiv);
        }
        if (messageId) {
          asstDiv.id = 'message-' + messageId;
          asstDiv.dataset.messageId = messageId;
          window._streamingMessageId = messageId;
        }
        await refreshMessagesAfterStream(chatId, userMessageId, messageId);
        window._streamingMessageId = null;
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let messageId = null;
      let userMessageId = null;
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
            if (json.user_message_id) {
              const userDiv = asstDiv.previousElementSibling;
              if (userDiv && userDiv.classList.contains('message')) {
                userDiv.id = 'message-' + json.user_message_id;
              }
            }
          } else if (json.token !== undefined) {
            fullText += json.token;
            const contentDiv = asstDiv.querySelector('.message-content');
            if (contentDiv) {
              preserveOpenStates(contentDiv, () => window.renderMessage(fullText));
              _updateReasoningButton(contentDiv);

              if (window.autoScroll && window.scrollSentinel) {
                window.scrollSentinel.scrollIntoView({ behavior: 'instant' });
              }
            }
          } else if (json.error) {
            throw new Error(json.error);
          } else if (json.done) {
            messageId = json.message_id;
          }
        }
      }

      const contentDiv = asstDiv.querySelector('.message-content');
      if (contentDiv) {
        preserveOpenStates(contentDiv, () => window.renderMessage(fullText));
        _updateReasoningButton(contentDiv);
      }
      if (messageId) {
        asstDiv.id = 'message-' + messageId;
        asstDiv.dataset.messageId = messageId;
      }

      await refreshMessagesAfterStream(chatId, userMessageId, messageId);

      const doneProvider =
        window.APP_PROVIDERS && window.APP_PROVIDERS.find((p) => p.id === providerId);
      if (
        doneProvider &&
        doneProvider.type === 'openrouter' &&
        doneProvider.model &&
        doneProvider.model.startsWith('anthropic/claude')
      ) {
        const doneSamplers = body.samplers || {};
        if (doneSamplers.cache_enabled) {
          localStorage.setItem('focus-cache-time-' + providerId, Date.now().toString());
          localStorage.setItem(
            'focus-cache-ttl-' + providerId,
            doneSamplers.cache_ttl || 'ephemeral',
          );
        }
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        const errorToast = document.getElementById('error-toast');
        const errorToastText = document.getElementById('error-toast-text');
        if (errorToast && errorToastText) {
          errorToastText.innerText = err.message;
          errorToast.classList.remove('hidden');
        }

        if (asstDiv && asstDiv.parentNode) {
          asstDiv.remove();
        }

        htmx.ajax('GET', api.partials.messageList(chatId), {
          target: '#message-list',
          swap: 'innerHTML',
        });
      } else if (!fullText) {
        if (isRegen) {
          htmx.ajax('GET', api.partials.messageList(chatId), {
            target: '#message-list',
            swap: 'innerHTML',
          });
        } else if (asstDiv && asstDiv.parentNode) {
          asstDiv.remove();
        }
      } else if (messageId) {
        const partialText = fullText;
        await refreshMessagesAfterStream(chatId, userMessageId, messageId);
        if (partialText) {
          const restoredDiv = document.getElementById('message-' + messageId);
          if (restoredDiv) {
            restoredDiv.dataset.rawContent = partialText;
            const restoredContent = restoredDiv.querySelector('.message-content');
            if (restoredContent) {
              restoredContent.innerHTML = window.renderMessage(partialText);
              _updateReasoningButton(restoredContent);
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

      const asstDiv = window.createAssistantPlaceholderDiv(charName, charImagePath);
      messageList.insertBefore(asstDiv, window.scrollSentinel);
      asstDiv.scrollIntoView({ behavior: 'smooth' });

      window.triggerGeneration(chatId, asstDiv, false);
      return;
    }

    const text = input.value.trim();
    if (!text && window.stagedFiles.length === 0) return;
    if (!providerId) {
      alert('No provider configured. Add one in Providers.');
      return;
    }

    const dataList = document.getElementById('message-list-data');
    const personaName = dataList ? dataList.getAttribute('data-persona-name') || 'You' : 'You';
    const personaAvatar = dataList ? dataList.getAttribute('data-persona-avatar') || '' : '';

    const userDiv = window.createUserMessageDiv(text, window.stagedFiles, personaName, personaAvatar);
    messageList.insertBefore(userDiv, window.scrollSentinel);

    window._tempUserMessage = text;

    input.value = '';
    resizeTextarea(input);

    const charName = dataList ? dataList.getAttribute('data-char-name') : 'Assistant';
    const charImagePath = dataList ? dataList.getAttribute('data-char-image') : '';

    const asstDiv = window.createAssistantPlaceholderDiv(charName, charImagePath);
    messageList.insertBefore(asstDiv, window.scrollSentinel);
    asstDiv.scrollIntoView({ behavior: 'smooth' });

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
      const r = await fetch(api.chatBranch(chatId, messageId), { method: 'POST' });
      if (!r.ok) throw new Error('Branch failed');
      const d = await r.json();
      window.location.href = '/chat/' + d.id;
    } catch (e) {
      alert(e.message);
    }
  };

  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.markdown-content').forEach(function (el) {
      const raw = el.textContent || '';
      el.innerHTML = window.renderMessage(raw);
      el.classList.add('processed');
    });
    syncReasoningButtons(document);

    document.getElementById('message-list')?.classList.add('ready');

    const savedProvider = StateManager.get('provider_id');
    if (savedProvider) {
      const sendBtn = document.getElementById('send-btn');
      if (sendBtn) sendBtn.dataset.providerId = savedProvider;
    }
  });

  document.addEventListener('mousedown', function (e) {
    if (e.target && e.target.tagName === 'SUMMARY') {
      const details = e.target.closest('details.reasoning');
      if (details) {
        e.preventDefault();
        if (details.hasAttribute('open')) {
          details.removeAttribute('open');
        } else {
          details.setAttribute('open', '');
        }
      }
    }
  });

  document.addEventListener('click', function (e) {
    if (e.target && e.target.tagName === 'SUMMARY' && e.target.closest('details.reasoning')) {
      e.preventDefault();
    }
  });

  document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (evt.detail.target.id === 'message-list') {
      evt.detail.target.querySelectorAll('.markdown-content').forEach(function (el) {
        const raw = el.textContent || '';
        el.innerHTML = window.renderMessage(raw);
        el.classList.add('processed');
      });
      syncReasoningButtons(evt.detail.target);
      if (typeof updateSendButtonState === 'function') {
        updateSendButtonState();
      }

      window.ensureSentinelAndObserver();
    }
  });
})();
