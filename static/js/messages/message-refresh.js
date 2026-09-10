(function () {
  function _replaceMessageNode(doc, msgId) {
    var id = MessageIdentity.bare(msgId);
    var newMsg = doc.getElementById(MessageIdentity.domId(id));
    if (!newMsg) return;

    var oldMsg = MessageIdentity.node(id) || MessageIdentity.placeholder(id);
    if (!oldMsg) return;

    newMsg.style.setProperty('animation', 'none', 'important');
    oldMsg.replaceWith(newMsg);
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

  // The one full-list renderer. Fetches the server-rendered partial and
  // rearranges the DOM to match it in place, so scroll position, open reasoning
  // toggles, and pruned stubs survive. *changedIds* are re-rendered from the
  // server; pass null to re-render every message.
  async function refreshMessageList(chatId, changedIds) {
    var container = document.getElementById('message-list');
    if (!container) return;

    var resp = await window.hxFetch(window.api.partials.messageList(chatId));
    if (!resp.ok) return;
    var doc = new DOMParser().parseFromString(await resp.text(), 'text/html');

    var orderedIds = Array.prototype.map.call(doc.querySelectorAll('.message'), function (n) {
      return n.id;
    });

    var newData = doc.getElementById('message-list-data');
    var oldData = container.querySelector('#message-list-data');
    if (newData && oldData) oldData.replaceWith(newData);

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
      _replaceMessageNode(doc, toReplace[i]);
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
    }

    if (window.processMessageList) window.processMessageList(container);
    if (window.reapplyDeleteMode) window.reapplyDeleteMode();

    _refreshChatList(chatId);
    if (window.pruneMessages) window.pruneMessages();
  }
  window.refreshMessageList = refreshMessageList;

  async function refreshMessagesAfterStream(chatId, userMsgId, asstMsgId) {
    await refreshMessageList(chatId, [userMsgId, asstMsgId].filter(Boolean));
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
      await refreshMessageList(chatId, [messageId]);
      return;
    }

    var msgIndex = parseInt(existingMsg.getAttribute('data-msg-index')) || 1;
    var msgList = document.getElementById('message-list');
    var msgs = msgList ? msgList.querySelectorAll('.message') : [];
    var isLatest = msgs.length > 0 ? existingMsg === msgs[msgs.length - 1] : false;
    var url = '/partials/message/' + chatId + '/' + messageId
      + '?msg_index=' + msgIndex + '&is_latest=' + isLatest;
    var resp = await window.hxFetch(url);
    if (!resp.ok) return;

    var doc = new DOMParser().parseFromString(await resp.text(), 'text/html');
    _replaceMessageNode(doc, messageId);
    if (window.processMessageList) window.processMessageList(document.getElementById('message-list'));
    _refreshChatList(chatId);
  }
  window.refreshSingleMessage = refreshSingleMessage;

  // Full re-render of the message list. Use this whenever client and server may
  // disagree about *which* messages exist (or their order) — a single-node
  // refresh only patches content of nodes both sides already have.
  window.refreshChatMessages = function (chatId) {
    return refreshMessageList(chatId, null);
  };
})();
