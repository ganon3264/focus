(function () {
  function _updateReasoningButton(contentDiv) {
    const msg = contentDiv.closest('.message');
    if (!msg) return;
    const btn = msg.querySelector('.reasoning-toggle-btn');
    if (!btn) return;
    const hasReasoning = contentDiv.querySelector('details.reasoning');
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
    container.querySelectorAll('details.reasoning[open]').forEach((d) => {
      if (d.dataset.thinkId) openStates.add(d.dataset.thinkId);
    });
    container.innerHTML = renderFn();
    openStates.forEach((id) => {
      const el = container.querySelector(`details.reasoning[data-think-id="${id}"]`);
      if (el) el.setAttribute('open', '');
    });
  }
  window.preserveOpenStates = preserveOpenStates;

  document.addEventListener('mousedown', function (e) {
    if (e.target && e.target.tagName === 'SUMMARY') {
      const details = e.target.closest('details.reasoning');
      if (details) {
        e.preventDefault();
        if (details.hasAttribute('open')) {
          details.removeAttribute('open');
        } else {
          details.setAttribute('open', '');
        }
      }
    }
  });

  document.addEventListener('click', function (e) {
    if (e.target && e.target.tagName === 'SUMMARY' && e.target.closest('details.reasoning')) {
      e.preventDefault();
    }
  });
})();
