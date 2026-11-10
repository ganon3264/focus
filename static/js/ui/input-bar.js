(function () {
  var sendBtn = document.getElementById('send-btn');
  var input = document.getElementById('chat-input');

  // Height is driven by the content, never by a constant: `auto` lets the
  // browser report the box the CSS already defines (one line + padding), so the
  // first keystroke cannot make the composer jump a size.
  function resizeTextarea(el) {
    var maxH = parseFloat(getComputedStyle(el).maxHeight) || 248;
    // Firefox folds the placeholder into scrollHeight, and the engraved
    // placeholder line is a hair taller than a line of body text — measuring it
    // shrinks the composer on the first keystroke. Measure the text alone.
    var placeholder = el.placeholder;
    el.placeholder = '';
    el.style.height = 'auto';
    var needed = el.scrollHeight;
    el.placeholder = placeholder;
    el.style.height = Math.min(maxH, needed) + 'px';
    el.style.overflowY = needed > maxH ? 'auto' : 'hidden';
  }

  function updateSendButtonState() {
    if (!sendBtn || !input) return;
    var text = input.value.trim();
    // The last role comes from the server-rendered list metadata, not from
    // scanning DOM nodes (which can lag behind the server after a stop).
    var dataList = document.getElementById('message-list-data');
    var lastRole = dataList ? dataList.getAttribute('data-last-role') || '' : '';
    var isReplyMode = !text && (!window.stagedFiles || window.stagedFiles.length === 0) && lastRole === 'user';
    var newMode = isReplyMode ? 'reply' : 'send';

    if (sendBtn.dataset.mode !== newMode) {
      sendBtn.innerHTML = window.getSvgSprite(isReplyMode ? 'regen' : 'send', 18);
      sendBtn.title = isReplyMode ? 'Generate reply' : 'Send message';
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
