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

  function _playAudio(base64, mime) {
    var bin = atob(base64);
    var bytes = new Uint8Array(bin.length);
    for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    var url = URL.createObjectURL(new Blob([bytes], { type: mime }));
    var a = new Audio(url);
    a.onended = function () { URL.revokeObjectURL(url); };
    a.play().catch(function () {});
  }

  // Delegate to the run response: an audio ``files`` entry is played in the
  // browser, not persisted to the message (which would feed it back to the
  // model as input_audio on later turns).
  function playReturnedAudio(data) {
    var f = (data.files || []).find(function (x) {
      return x.mime && x.mime.indexOf('audio/') === 0;
    });
    if (f) _playAudio(f.data, f.mime);
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
        playReturnedAudio(data);
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
