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
    const openStates = new Set();
    container.querySelectorAll('.reasoning-block.open').forEach((d) => {
      if (d.dataset.thinkId) openStates.add(d.dataset.thinkId);
    });
    container.innerHTML = renderFn();
    openStates.forEach((id) => {
      const el = container.querySelector(`.reasoning-block[data-think-id="${id}"]`);
      if (el) {
        el.classList.add('open');
        const btn = el.querySelector('.reasoning-summary');
        if (btn) btn.setAttribute('aria-expanded', 'true');
        const content = el.querySelector('.reasoning-content');
        if (content) content.classList.remove('hidden');
      }
    });
  }
  window.preserveOpenStates = preserveOpenStates;

  window.toggleReasoningBlock = function (btn) {
    const block = btn.closest('.reasoning-block');
    if (!block) return;
    const content = block.querySelector('.reasoning-content');
    if (!content) return;
    const isOpen = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!isOpen));
    content.classList.toggle('hidden', isOpen);
    block.classList.toggle('open', !isOpen);
  };
})();
