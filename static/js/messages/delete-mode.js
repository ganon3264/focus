(function () {
  // Delete-mode selection is an id set, not the DOM. Culling stays active while
  // the toolbar is up, so a selected row can be replaced by a placeholder and
  // restored later without losing its state.
  var selectedIds = new Set();
  var active = false;

  function renderCount() {
    var countEl = document.getElementById('delete-selected-count');
    if (countEl) countEl.textContent = String(selectedIds.size);
    var btn = document.getElementById('delete-selected-btn');
    if (btn) btn.disabled = selectedIds.size === 0;
  }

  // Only the checkbox that changed, so ids that are currently culled are not
  // dropped from the selection.
  function updateDeleteSelection(cb) {
    if (cb) {
      if (cb.checked) selectedIds.add(cb.value);
      else selectedIds.delete(cb.value);
    }
    renderCount();
  }
  window.updateDeleteSelection = updateDeleteSelection;

  window.isDeleteModeActive = function () {
    return active;
  };

  // Apply the delete-mode chrome to one node. Used for live messages and for
  // nodes the pruner restores as they scroll back into view.
  window.applyDeleteModeToNode = function (msg) {
    if (!active || !msg) return;
    var id = msg.dataset.messageId;
    var box = msg.querySelector('[data-ui="delete-mode-checkbox"]');
    if (box) box.classList.remove('hidden');
    var cb = msg.querySelector('[data-ui="msg-select-checkbox"]');
    if (cb) cb.checked = !!(id && selectedIds.has(id));
    var actions = msg.querySelector('[data-ui="toolbar"]');
    if (actions) actions.classList.add('hidden');
    msg.classList.add('is-deleting');
  };

  function applyToLiveMessages() {
    document.querySelectorAll('[data-ui="message"]').forEach(function (msg) {
      window.applyDeleteModeToNode(msg);
    });
  }

  window.enterDeleteMode = function (startMessageId) {
    active = true;
    document.getElementById('standard-input-container').classList.add('hidden');
    document.getElementById('delete-toolbar').classList.remove('hidden');
    document.getElementById('delete-toolbar').classList.add('flex');

    if (startMessageId) {
      // "This message and everything after" spans culled rows too, so walk the
      // ordered children (live nodes + placeholders), not just `.message`.
      selectedIds.clear();
      var container = document.getElementById('message-list');
      var nodes = container ? Array.prototype.filter.call(container.children, function (el) {
        return el.matches('[data-ui="message"]') || el.matches('[data-ui="message-placeholder"]');
      }) : [];
      var foundStart = false;
      nodes.forEach(function (node) {
        var id = MessageIdentity.bare(node);
        if (!id) return;
        if (!foundStart && id === startMessageId) foundStart = true;
        if (foundStart) selectedIds.add(id);
      });
    }

    applyToLiveMessages();
    renderCount();
  };

  // Re-apply delete mode after a message-list render. The renderer calls this
  // directly; it repaints the current selection and never recomputes a range.
  window.reapplyDeleteMode = function () {
    if (active) window.enterDeleteMode();
  };

  window.exitDeleteMode = function () {
    active = false;
    selectedIds.clear();

    document.getElementById('delete-toolbar').classList.remove('flex');
    document.getElementById('delete-toolbar').classList.add('hidden');
    document.getElementById('standard-input-container').classList.remove('hidden');

    document.querySelectorAll('[data-ui="toolbar"]').forEach(function (el) { el.classList.remove('hidden'); });
    document.querySelectorAll('[data-ui="message"]').forEach(function (el) { el.classList.remove('is-deleting'); });
    document.querySelectorAll('[data-ui="delete-mode-checkbox"]').forEach(function (el) { el.classList.add('hidden'); });
    document.querySelectorAll('[data-ui="msg-select-checkbox"]').forEach(function (cb) { cb.checked = false; });

    renderCount();
    if (typeof updateSendButtonState === 'function') updateSendButtonState();
  };

  window.bulkDeleteSelected = async function (chatId) {
    var selected = Array.from(selectedIds);
    if (selected.length === 0) {
      window.exitDeleteMode();
      return;
    }

    window.customConfirm('Delete ' + selected.length + ' message(s)?', async function () {
      try {
        var res = await hxJson(window.api.chatBulkDelete(chatId), 'POST', { message_ids: selected });
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
