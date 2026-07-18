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
  };

  window.bulkDeleteSelected = async function (chatId) {
    const selected = Array.from(document.querySelectorAll('.msg-select-checkbox:checked')).map(
      (cb) => cb.value,
    );
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
          htmx.ajax('GET', window.api.partials.messageList(chatId), {
            target: '#message-list',
            swap: 'innerHTML',
          });
          if (window._refreshChatList) window._refreshChatList(chatId);
        } else {
          alert('Failed to delete messages');
        }
      } catch (e) {
        console.error(e);
      }

      window.exitDeleteMode();
    });
  };

  document.body.addEventListener('htmx:afterSettle', function (e) {
    if (e.target.id === 'message-list') {
      const toolbar = document.getElementById('delete-toolbar');
      if (toolbar && !toolbar.classList.contains('hidden')) {
        window.enterDeleteMode();
      }
    }
  });
})();
