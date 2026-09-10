(function () {
  function _processNode(node, inDeleteMode) {
    if (window.htmx && window.htmx.process) window.htmx.process(node);
    node.querySelectorAll('.markdown-content:not(.processed)').forEach(function (el) {
      el.innerHTML = window.renderMessage(el.textContent || '');
      el.classList.add('processed');
    });
    if (window.syncReasoningButtons) window.syncReasoningButtons(node);
    if (inDeleteMode) {
      var cb = node.querySelector('.delete-mode-checkbox');
      if (cb) cb.classList.remove('hidden');
      var actions = node.querySelector('.normal-mode-actions');
      if (actions) actions.classList.add('hidden');
    }
    if (window.formatTimestamps) window.formatTimestamps();
  }

  function _inDeleteMode() {
    var bar = document.getElementById('delete-toolbar');
    return !!(bar && !bar.classList.contains('hidden'));
  }

  function _replaceMessageNode(doc, msgId, inDeleteMode) {
    var id = MessageIdentity.bare(msgId);
    var newMsg = doc.getElementById(MessageIdentity.domId(id));
    if (!newMsg) return;

    var oldMsg = MessageIdentity.node(id) || MessageIdentity.placeholder(id);
    if (!oldMsg) return;

    newMsg.style.setProperty('animation', 'none', 'important');
    oldMsg.replaceWith(newMsg);
    _processNode(newMsg, inDeleteMode);
    if (window._forgetPruned) window._forgetPruned(id);
  }

  function _findLiveNode(container, id) {
    var node = MessageIdentity.node(id);
    if (node && node.parentNode === container) return node;
    return MessageIdentity.placeholder(id, container);
  }

  // Reorder the container's message nodes to match *orderedIds* (the server's
  // position order): reuse live nodes, insert missing ones via *createNode*,
  // drop nodes the server no longer has, and keep the sentinel last. Returns
  // the freshly inserted nodes so the caller can post-process them.
  function _reconcileOrder(container, orderedIds, dataDiv, sentinel, getNode, createNode) {
    var inserted = [];
    var cursor = dataDiv ? dataDiv.nextElementSibling : container.firstElementChild;

    orderedIds.forEach(function (id) {
      var node = getNode(id);
      var isNew = false;
      if (!node) {
        node = createNode(id);
        isNew = true;
      }
      if (!node) return;
      if (node !== cursor) container.insertBefore(node, cursor);
      if (isNew) inserted.push(node);
      cursor = node.nextElementSibling;
    });

    var wanted = {};
    orderedIds.forEach(function (id) { wanted[id] = true; });

    var extras = container.querySelectorAll('.message');
    for (var i = extras.length - 1; i >= 0; i--) {
      if (!wanted[extras[i].id]) extras[i].remove();
    }
    var placeholders = container.querySelectorAll('.message-placeholder');
    for (var j = placeholders.length - 1; j >= 0; j--) {
      var ph = placeholders[j];
      if (!wanted[MessageIdentity.domId(ph.dataset.msgId)]) {
        if (window._forgetPruned) window._forgetPruned(ph.dataset.msgId);
        ph.remove();
      }
    }

    if (sentinel && container.children[container.children.length - 1] !== sentinel) {
      container.appendChild(sentinel);
    }
    return inserted;
  }
  window._reconcileOrder = _reconcileOrder;

  // Server-authoritative refresh: the server renders the ordered list, and the
  // DOM is rearranged to match it instead of trusting the order nodes happened
  // to be appended in. *changedIds* are re-rendered from the server; pass null
  // to re-render every message.
  async function _reconcileMessageList(chatId, changedIds) {
    var container = document.getElementById('message-list');
    if (!container) return;

    var resp = await fetch(window.api.partials.messageList(chatId));
    if (!resp.ok) return;
    var doc = new DOMParser().parseFromString(await resp.text(), 'text/html');

    var orderedIds = Array.prototype.map.call(doc.querySelectorAll('.message'), function (n) {
      return n.id;
    });

    var newData = doc.getElementById('message-list-data');
    var oldData = container.querySelector('#message-list-data');
    if (newData && oldData) oldData.replaceWith(newData);

    var inDeleteMode = _inDeleteMode();

    // When the live node set diverges from the server's (a message the client
    // never saw, or one it thinks still exists), re-render every message so
    // per-message state like `data-msg-index` stays correct.
    var liveCount = container.querySelectorAll('.message').length
      + container.querySelectorAll('.message-placeholder').length;
    var missing = orderedIds.some(function (id) { return !_findLiveNode(container, id); });
    var toReplace = (changedIds == null || missing || liveCount !== orderedIds.length)
      ? orderedIds.map(function (id) { return MessageIdentity.bare(id); })
      : changedIds;
    for (var i = 0; i < toReplace.length; i++) {
      _replaceMessageNode(doc, toReplace[i], inDeleteMode);
    }

    var inserted = _reconcileOrder(
      container,
      orderedIds,
      container.querySelector('#message-list-data'),
      container.querySelector('#scroll-sentinel'),
      function (id) { return _findLiveNode(container, id); },
      function (id) { return doc.getElementById(id); },
    );

    for (var k = 0; k < inserted.length; k++) {
      inserted[k].style.setProperty('animation', 'none', 'important');
      _processNode(inserted[k], inDeleteMode);
    }

    _refreshChatList(chatId);
    if (window.postSwapProcess) window.postSwapProcess(container);
    if (window.pruneMessages) window.pruneMessages();
  }

  async function refreshMessagesAfterStream(chatId, userMsgId, asstMsgId) {
    await _reconcileMessageList(chatId, [userMsgId, asstMsgId].filter(Boolean));
  }
  window.refreshMessagesAfterStream = refreshMessagesAfterStream;

  window._refreshChatList = function (chatId) {
    var params = '?current_chat_id=' + encodeURIComponent(chatId);
    var charId = StateManager.get('character_id');
    if (charId) params += '&character_id=' + encodeURIComponent(charId);
    hxGet(window.api.partials.chatList + params, {
      target: '#chat-list',
      swap: 'innerHTML',
    });
  };

  // Swipe/edit/extension updates never change order, so they keep the cheaper
  // single-node endpoint. A node that is gone (pruned away) falls back to the
  // full reconcile.
  async function refreshSingleMessage(chatId, messageId) {
    var existingMsg = MessageIdentity.node(messageId);
    if (!existingMsg) {
      await _reconcileMessageList(chatId, [messageId]);
      return;
    }

    var msgIndex = parseInt(existingMsg.getAttribute('data-msg-index')) || 1;
    var msgList = document.getElementById('message-list');
    var msgs = msgList ? msgList.querySelectorAll('.message') : [];
    var isLatest = msgs.length > 0 ? existingMsg === msgs[msgs.length - 1] : false;
    var url = '/partials/message/' + chatId + '/' + messageId
      + '?msg_index=' + msgIndex + '&is_latest=' + isLatest;
    var resp = await fetch(url);
    if (!resp.ok) return;

    var doc = new DOMParser().parseFromString(await resp.text(), 'text/html');
    _replaceMessageNode(doc, messageId, _inDeleteMode());
    _refreshChatList(chatId);
    if (window.postSwapProcess) window.postSwapProcess(document.getElementById('message-list'));
  }
  window.refreshSingleMessage = refreshSingleMessage;

  // Full re-render of the message list. Use this whenever client and server may
  // disagree about *which* messages exist (or their order) — a single-node
  // refresh only patches content of nodes both sides already have.
  window.refreshChatMessages = function (chatId) {
    return hxGet(window.api.partials.messageList(chatId), {
      target: '#message-list',
      swap: 'innerHTML',
    });
  };
})();
