(function () {
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
    window.syncReasoningButtons(newMsg);
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

  async function _refreshMessageNodes(chatId, msgIds) {
    if (msgIds.length === 0) return;

    var existingMsg = document.getElementById('message-' + msgIds[0]);
    var doc;
    if (existingMsg && msgIds.length === 1) {
      var msgIndex = parseInt(existingMsg.getAttribute('data-msg-index')) || 1;
      var msgList = document.getElementById('message-list');
      var msgs = msgList ? msgList.querySelectorAll('.message') : [];
      var isLatest = msgs.length > 0 ? existingMsg === msgs[msgs.length - 1] : false;
      var url = '/partials/message/' + chatId + '/' + msgIds[0] + '?msg_index=' + msgIndex + '&is_latest=' + isLatest;
      var resp = await fetch(url);
      if (!resp.ok) return;
      doc = new DOMParser().parseFromString(await resp.text(), 'text/html');
    } else {
      var resp = await fetch(window.api.partials.messageList(chatId));
      if (!resp.ok) return;
      doc = new DOMParser().parseFromString(await resp.text(), 'text/html');
      var newSentinel = doc.getElementById('message-list-data');
      var oldSentinel = document.getElementById('message-list-data');
      if (newSentinel && oldSentinel) oldSentinel.replaceWith(newSentinel);
    }

    var inDeleteMode = document.getElementById('delete-toolbar') &&
      !document.getElementById('delete-toolbar').classList.contains('hidden');

    for (var i = 0; i < msgIds.length; i++) {
      _replaceMessageNode(doc, msgIds[i], inDeleteMode);
    }

    _refreshChatList(chatId);
    if (window._postSwapProcess) window._postSwapProcess(document.getElementById('message-list'));
  }

  async function refreshMessagesAfterStream(chatId, userMsgId, asstMsgId) {
    await _refreshMessageNodes(chatId, [userMsgId, asstMsgId].filter(Boolean));
  }
  window.refreshMessagesAfterStream = refreshMessagesAfterStream;

  window._refreshChatList = function (chatId) {
    var params = '?current_chat_id=' + encodeURIComponent(chatId);
    var charId = StateManager.get('character_id');
    if (charId) params += '&character_id=' + encodeURIComponent(charId);
    htmx.ajax('GET', window.api.partials.chatList + params, {
      target: '#chat-list',
      swap: 'innerHTML',
    });
  };

  async function refreshSingleMessage(chatId, messageId) {
    await _refreshMessageNodes(chatId, [messageId]);
  }
  window.refreshSingleMessage = refreshSingleMessage;
})();
