(function () {
  window.updateContinueButtons = function () {
    var type = StateManager.get('provider_type');
    var caps = (window.ProviderSchema && ProviderSchema.capabilities(type)) || {};
    // Continue is only meaningful where the provider accepts a prefill.
    var noPrefill = caps.supports_prefill === false;
    document.querySelectorAll('.continue-btn').forEach(function (btn) {
      btn.classList.toggle('hidden', noPrefill);
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
    if (window.isDeleteModeActive && window.isDeleteModeActive() && window.applyDeleteModeToNode) {
      container.querySelectorAll('.message').forEach(function (msg) {
        window.applyDeleteModeToNode(msg);
      });
    }
    if (typeof updateSendButtonState === 'function') updateSendButtonState();
    if (typeof updateContinueButtons === 'function') updateContinueButtons();
    window.ensureSentinelAndObserver();
  };
})();
