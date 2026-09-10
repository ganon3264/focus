(function () {
  function inDeleteMode() {
    var bar = document.getElementById('delete-toolbar');
    return !!(bar && !bar.classList.contains('hidden'));
  }

  window.updateContinueButtons = function () {
    var type = StateManager.get('provider_type');
    var isGoogle = type === 'google_aistudio' || type === 'google_vertex';
    document.querySelectorAll('.continue-btn').forEach(function (btn) {
      btn.classList.toggle('hidden', isGoogle);
    });
  };

  // The single post-render pass for message content. Both the in-place
  // reconcile and htmx-swapped partials land here, so markdown, reasoning,
  // timestamps, delete-mode visibility, and toolbar state are applied in one
  // place instead of being duplicated per refresh path.
  window.processMessageList = function (container) {
    if (!container) return;
    if (window.htmx && window.htmx.process) window.htmx.process(container);
    container.querySelectorAll('.markdown-content:not(.processed)').forEach(function (el) {
      el.innerHTML = window.renderMessage(el.textContent || '');
      el.classList.add('processed');
    });
    if (window.syncReasoningButtons) window.syncReasoningButtons(container);
    if (window.formatTimestamps) window.formatTimestamps();
    if (inDeleteMode()) {
      container.querySelectorAll('.message').forEach(function (msg) {
        var cb = msg.querySelector('.delete-mode-checkbox');
        if (cb) cb.classList.remove('hidden');
        var actions = msg.querySelector('.normal-mode-actions');
        if (actions) actions.classList.add('hidden');
      });
    }
    if (typeof updateSendButtonState === 'function') updateSendButtonState();
    if (typeof updateContinueButtons === 'function') updateContinueButtons();
    window.ensureSentinelAndObserver();
  };
})();
