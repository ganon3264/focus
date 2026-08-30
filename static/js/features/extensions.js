(function () {
  function toastLogs(logs) {
    (logs || []).forEach(function (log) {
      var msg = log.level === 'error' ? 'showErrorToast'
        : log.level === 'success' ? 'showSuccessToast'
        : log.level === 'warning' ? 'showToast'
        : 'showInfoToast';
      if (window[msg]) window[msg](log.message || '');
    });
  }

  // Called via data-action="actionRunExtension" on message toolbar buttons.
  window.actionRunExtension = function (el) {
    var name = el.dataset.extName;
    if (!name) return;
    var msg = el.closest('.message');
    var messageId = msg.dataset.messageId;
    var chatId = msg.dataset.chatId || StateManager.get('chat_id');
    if (!messageId || !chatId) return;

    el.classList.add('disabled', 'opacity-50');
    window.showInfoToast('Running ' + name + '…');

    fetch('/api/extensions/' + encodeURIComponent(name) + '/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: chatId, message_id: messageId }),
    })
      .then(function (r) {
        if (!r.ok) {
          return r.json().then(function (d) {
            throw new Error(d.detail || d.error || 'Extension failed');
          }).catch(function (e) {
            if (e instanceof SyntaxError) throw new Error('Extension failed (' + r.status + ')');
            throw e;
          });
        }
        return r.json();
      })
      .then(function (data) {
        toastLogs(data.logs);
        if (data.status === 'error') {
          window.showErrorToast(data.error || 'Extension failed');
          return;
        }
        if (data.content && data.logs && !data.logs.length) {
          window.showInfoToast(String(data.content).slice(0, 200));
        }
        if (data.swipe_created || data.attachments_added > 0) {
          window.refreshSingleMessage(chatId, messageId);
        }
      })
      .catch(function (e) {
        window.showErrorToast(e.message || 'Extension failed');
      })
      .finally(function () {
        el.classList.remove('disabled', 'opacity-50');
      });
  };
})();
