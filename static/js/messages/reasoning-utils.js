(function () {
  function _updateReasoningButton(contentDiv) {
    const msg = contentDiv.closest('.message');
    if (!msg) return;
    let btn = msg.querySelector('.reasoning-toggle-btn');

    // The header button only controls the index-0 reasoning block (a plain div,
    // not a <details>). Later reasoning blocks have their own inline toggles.
    const blocks = msg.querySelectorAll('.reasoning-block');
    let hasFirstReasoning = false;
    for (let i = 0; i < blocks.length; i++) {
      if (!blocks[i].classList.contains('details')) {
        hasFirstReasoning = true;
        break;
      }
    }

    if (!hasFirstReasoning) {
      if (btn) btn.classList.add('hidden');
      return;
    }
    if (!btn && window.ensureReasoningToggleButton) {
      btn = window.ensureReasoningToggleButton(msg);
    }
    if (!btn) return;
    btn.classList.remove('hidden');
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

  window.toggleReasoning = function (btn) {
    const msg = btn.closest('.msg') || btn.closest('.message');
    if (!msg) return;
    const block = msg.querySelector('.reasoning-block:not(.details)');
    if (!block) return;
    const content = block.querySelector('.reasoning-content');
    const isOpen = !msg.classList.contains('reasoning-open');
    if (isOpen && content && !content.classList.contains('processed')) {
      content.innerHTML = DOMPurify.sanitize(marked.parse(content.textContent || '', { breaks: true }));
      content.classList.add('processed');
    }
    if (content) content.classList.toggle('hidden', !isOpen);
    msg.classList.toggle('reasoning-open', isOpen);
  };
})();
