(function () {
  function _updateReasoningButton(contentDiv) {
    const msg = contentDiv.closest('.message');
    if (!msg) return;
    const btn = msg.querySelector('.reasoning-toggle-btn');
    if (!btn) return;
    const hasReasoning = msg.querySelector('.reasoning-block');
    btn.classList.toggle('hidden', !hasReasoning);
  }
  window._updateReasoningButton = _updateReasoningButton;

  function syncReasoningButtons(container) {
    if (!container) return;
    container.querySelectorAll('.message-content').forEach((el) => _updateReasoningButton(el));
  }
  window.syncReasoningButtons = syncReasoningButtons;

  function preserveOpenStates(container, renderFn) {
    const openIds = new Set();
    container.querySelectorAll('.details.reasoning-block[open]').forEach((d) => {
      if (d.dataset.thinkId) openIds.add(d.dataset.thinkId);
    });
    const msg = container.closest('.msg');
    const firstWasOpen = msg ? msg.classList.contains('reasoning-open') : false;
    container.innerHTML = renderFn();
    openIds.forEach((id) => {
      const el = container.querySelector(`[data-think-id="${id}"]`);
      if (el) el.setAttribute('open', '');
    });
    if (firstWasOpen) {
      const first = container.querySelector('.reasoning-block:not(.details)');
      if (first) {
        const content = first.querySelector('.reasoning-content');
        if (content) content.classList.remove('hidden');
      }
    }
  }
  window.preserveOpenStates = preserveOpenStates;
})();
