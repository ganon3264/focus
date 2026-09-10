(function () {
  let lastDeleteSelection = [];

  function updateDeleteSelection() {
    const selectedCbs = document.querySelectorAll('.msg-select-checkbox:checked');
    lastDeleteSelection = Array.from(selectedCbs).map((cb) => cb.value);
    const countEl = document.getElementById('delete-selected-count');
    if (countEl) countEl.textContent = lastDeleteSelection.length;
  }
  window.updateDeleteSelection = updateDeleteSelection;

  window.enterDeleteMode = function (startMessageId) {
    document.getElementById('standard-input-container').classList.add('hidden');
    document.getElementById('delete-toolbar').classList.remove('hidden');
    document.getElementById('delete-toolbar').classList.add('flex');

    // Unprune every placeholder first so the visibility/selection pass below
    // sees all nodes — restored nodes carry their snapshot's hidden checkbox.
    document.querySelectorAll('.message-placeholder').forEach(function (ph) {
      var id = ph.dataset.msgId;
      if (id && window._unpruneMessage) window._unpruneMessage(id);
    });

    document.querySelectorAll('.normal-mode-actions').forEach((el) => el.classList.add('hidden'));
    document
      .querySelectorAll('.delete-mode-checkbox')
      .forEach((el) => el.classList.remove('hidden'));

    if (startMessageId) {
      let foundStart = false;
      document.querySelectorAll('.message').forEach((msgDiv) => {
        if (msgDiv.dataset.messageId === startMessageId) foundStart = true;
        const cb = msgDiv.querySelector('.msg-select-checkbox');
        if (cb) cb.checked = foundStart;
      });
    } else {
      document.querySelectorAll('.msg-select-checkbox').forEach((cb) => {
        if (lastDeleteSelection.includes(cb.value)) cb.checked = true;
      });
    }

    updateDeleteSelection();
  };

  // Re-apply delete mode after a message-list render. The renderer calls this
  // directly so it unprunes and restores selection the same way the htmx
  // swap's afterSettle hook used to.
  window.reapplyDeleteMode = function () {
    var bar = document.getElementById('delete-toolbar');
    if (bar && !bar.classList.contains('hidden')) window.enterDeleteMode();
  };

  window.exitDeleteMode = function () {
    document.getElementById('delete-toolbar').classList.remove('flex');
    document.getElementById('delete-toolbar').classList.add('hidden');
    document.getElementById('standard-input-container').classList.remove('hidden');

    document
      .querySelectorAll('.normal-mode-actions')
      .forEach((el) => el.classList.remove('hidden'));
    document.querySelectorAll('.delete-mode-checkbox').forEach((el) => el.classList.add('hidden'));

    document.querySelectorAll('.msg-select-checkbox').forEach((cb) => (cb.checked = false));
    lastDeleteSelection = [];
    if (typeof updateSendButtonState === 'function') updateSendButtonState();
  };

  window.bulkDeleteSelected = async function (chatId) {
    const selected = lastDeleteSelection;
    if (selected.length === 0) {
      window.exitDeleteMode();
      return;
    }

    window.customConfirm(`Delete ${selected.length} message(s)?`, async () => {
      try {
        const res = await fetch(window.api.chatBulkDelete(chatId), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message_ids: selected }),
        });
        if (res.ok) {
          if (window.refreshMessageList) {
            await window.refreshMessageList(chatId, null);
          } else if (window._refreshChatList) {
            window._refreshChatList(chatId);
          }
          window.showSuccessToast(selected.length + ' message' + (selected.length === 1 ? '' : 's') + ' deleted');
        } else {
          window.showErrorToast('Failed to delete messages');
        }
      } catch (e) {
        console.error(e);
      }

      window.exitDeleteMode();
    });
  };
})();
