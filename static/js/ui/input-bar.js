(function () {
  var sendBtn = document.getElementById('send-btn');
  var input = document.getElementById('chat-input');

  function resizeTextarea(el) {
    el.style.height = '44px';
    if (el.value === '') {
      el.style.overflowY = 'hidden';
      return;
    }
    var scrollHeight = el.scrollHeight;
    if (scrollHeight > 44) {
      el.style.height = Math.min(250, scrollHeight) + 'px';
    }
    el.style.overflowY = scrollHeight > 250 ? 'auto' : 'hidden';
  }

  function updateSendButtonState() {
    if (!sendBtn || !input) return;
    var text = input.value.trim();
    var msgs = document.querySelectorAll('#message-list .message');
    var lastRole = msgs.length > 0 ? msgs[msgs.length - 1].getAttribute('data-role') || '' : '';
    var isRegenMode = !text && (!window.stagedFiles || window.stagedFiles.length === 0) && lastRole === 'user';
    var newMode = isRegenMode ? 'regen' : 'send';

    if (sendBtn.dataset.mode !== newMode) {
      sendBtn.innerHTML = window.getSvgSprite(newMode, 18);
      sendBtn.title = isRegenMode ? 'Regenerate' : 'Send message';
      sendBtn.dataset.mode = newMode;
    }
  }

  window.resizeTextarea = resizeTextarea;
  window.updateSendButtonState = updateSendButtonState;

  if (input) {
    input.addEventListener('input', function () {
      resizeTextarea(this);
      updateSendButtonState();
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        if (sendBtn && !sendBtn.classList.contains('hidden')) {
          e.preventDefault();
          sendBtn.click();
        }
      }
    });
  }

  if (sendBtn) {
    updateSendButtonState();
  }
})();
