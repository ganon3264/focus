(function () {
  window.updateContinueButtons = function () {
    var type = StateManager.get('provider_type');
    var isGoogle = type === 'google_aistudio' || type === 'google_vertex';
    document.querySelectorAll('.continue-btn').forEach(function (btn) {
      btn.classList.toggle('hidden', isGoogle);
    });
  };

  window.postSwapProcess = function (container) {
    if (!container) return;
    container.querySelectorAll('.markdown-content:not(.processed)').forEach(function (el) {
      el.innerHTML = window.renderMessage(el.textContent || '');
      el.classList.add('processed');
    });
    if (window.syncReasoningButtons) window.syncReasoningButtons(container);
    if (typeof updateSendButtonState === 'function') updateSendButtonState();
    if (typeof updateContinueButtons === 'function') updateContinueButtons();
    window.ensureSentinelAndObserver();
  };
})();
