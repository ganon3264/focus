(function () {
  function _updateReasoningButton(contentDiv) {
    const msg = contentDiv.closest('[data-ui="message"]');
    if (!msg) return;
    let btn = msg.querySelector('[data-ui="reasoning-toggle-btn"]');

    // The header button only controls the index-0 reasoning block (a plain div,
    // not a <details>). Later reasoning blocks have their own inline toggles.
    const blocks = msg.querySelectorAll('[data-ui="reasoning-block"]');
    let hasFirstReasoning = false;
    for (let i = 0; i < blocks.length; i++) {
      if (blocks[i].tagName !== 'DETAILS') {
        hasFirstReasoning = true;
        break;
      }
    }

    if (!hasFirstReasoning) {
      if (btn) {
        btn.classList.add('hidden');
        const sep = btn.previousElementSibling;
        if (sep && sep.classList.contains('meta-sep')) sep.classList.add('hidden');
      }
      return;
    }
    if (!btn && window.ensureReasoningToggleButton) {
      btn = window.ensureReasoningToggleButton(msg);
    }
    if (!btn) return;
    btn.classList.remove('hidden');
    const sep = btn.previousElementSibling;
    if (sep && sep.classList.contains('meta-sep')) sep.classList.remove('hidden');
  }
  window._updateReasoningButton = _updateReasoningButton;

  function syncReasoningButtons(container) {
    if (!container) return;
    container.querySelectorAll('[data-ui~="message-content"]').forEach((el) => _updateReasoningButton(el));
  }
  window.syncReasoningButtons = syncReasoningButtons;

  function preserveOpenStates(container, renderFn) {
    const openIds = new Set();
    container.querySelectorAll('[data-ui="reasoning-block"][open]').forEach((d) => {
      if (d.dataset.thinkId) openIds.add(d.dataset.thinkId);
    });
    const msg = container.closest('[data-ui="message"]');
    const firstWasOpen = msg ? msg.classList.contains('reasoning-open') : false;
    container.innerHTML = renderFn();
    openIds.forEach((id) => {
      const el = container.querySelector(`[data-think-id="${id}"]`);
      if (el) el.setAttribute('open', '');
    });
    if (firstWasOpen) {
      const first = container.querySelector('[data-ui="reasoning-block"]:not(details)');
      if (first) {
        const content = first.querySelector('[data-ui~="reasoning-content"]');
        if (content) content.classList.remove('hidden');
      }
    }
  }
  window.preserveOpenStates = preserveOpenStates;

  // The one writer of the first (headless) block's open state: the class on the
  // message drives the rail toggle and the sticky pill, the `hidden` class on the
  // body drives the layout (a folded headless block is display:none).
  window.setReasoningOpen = function (msg, open) {
    const block = msg.querySelector('[data-ui="reasoning-block"]:not(details)');
    if (!block) return;
    const content = block.querySelector('[data-ui~="reasoning-content"]');
    if (open && content && !content.classList.contains('processed')) {
      content.innerHTML = DOMPurify.sanitize(marked.parse(content.textContent || '', { breaks: true }));
      content.classList.add('processed');
    }
    if (content) content.classList.toggle('hidden', !open);
    msg.classList.toggle('reasoning-open', open);
    if (window.syncStreamingView) window.syncStreamingView(msg);
    if (window.refreshStickyReasoning) window.refreshStickyReasoning();
    // Opening grows the turn, so a reader parked at the bottom stays there. The
    // resize observer usually does this, but the post-stream swap folds the
    // server node and reopens it inside one task: the list's height nets out to
    // nothing, no resize is reported — while the folded layout it passed through
    // already clamped the scroll. Pin here for that case.
    if (open && window.ChatScroll && window.ChatScroll.pinned()) window.ChatScroll.pin();
  };

  // The `reasoning_open` preference, read where the state is decided: `off`
  // leaves the block folded, `stream` unfolds it as it arrives, `keep` also
  // leaves it unfolded once the reply is a real message.
  window.reasoningOpensOnStream = function () {
    return !!(window.Prefs && window.Prefs.get('reasoning_open') !== 'off');
  };
  window.reasoningStaysOpen = function () {
    return !!(window.Prefs && window.Prefs.get('reasoning_open') === 'keep');
  };

  window.toggleReasoning = function (btn) {
    const msg = btn.closest('[data-ui="message"]');
    if (!msg) return;
    const block = msg.querySelector('[data-ui="reasoning-block"]:not(details)');
    if (!block) return;
    const isOpen = !msg.classList.contains('reasoning-open');
    const live = msg.parentNode ? msg.parentNode.querySelectorAll('[data-ui="message"]') : [];
    const isLast = live.length > 0 && live[live.length - 1] === msg;
    // Unfolding the live turn is growth like any other, so the pin follows it on
    // its own. Unfolding an older turn is the reader settling in to read it: that
    // growth is above the viewport, and following it would drag them off the
    // block they just opened.
    if (isOpen && !isLast && window.ChatScroll) window.ChatScroll.unpin();
    window.setReasoningOpen(msg, isOpen);
  };

  // Floating twin for the first reasoning block: the meta-row toggle keeps its
  // place (and chevron animation); once it scrolls above the chat viewport this
  // pill takes over at the top so a long block can still be collapsed.
  (function () {
    function initStickyReasoning() {
      const host = document.querySelector('#reasoning-sticky-host');
      const scroller = document.querySelector('[data-ui="chat-center"]');
      if (!host || !scroller || host.dataset.bound === '1') return;
      host.dataset.bound = '1';
      const pill = host.querySelector('[data-ui="reasoning-sticky-pill"]');
      let raf = null;

      function findActiveMessageId() {
        const top = scroller.getBoundingClientRect().top;
        const blocks = scroller.querySelectorAll('[data-ui="message"].reasoning-open [data-ui="reasoning-block"]:not(details)');
        for (const block of blocks) {
          const rect = block.getBoundingClientRect();
          if (rect.top < top && rect.bottom > top) {
            const msg = block.closest('[data-ui="message"]');
            return msg ? msg.dataset.messageId : null;
          }
        }
        return null;
      }

      function update() {
        raf = null;
        const id = findActiveMessageId();
        host.dataset.messageId = id || '';
        host.classList.toggle('hidden', !id);
      }

      function schedule() {
        if (raf === null) raf = requestAnimationFrame(update);
      }

      window.refreshStickyReasoning = update;
      scroller.addEventListener('scroll', schedule, { passive: true });
      window.addEventListener('resize', schedule);

      if (pill) {
        pill.addEventListener('click', function () {
          const id = host.dataset.messageId;
          if (!id) return;
          const msg = window.MessageIdentity ? MessageIdentity.node(id) : null;
          if (!msg) return;
          const btn = msg.querySelector('[data-ui="reasoning-toggle-btn"]');
          if (btn) window.toggleReasoning(btn);
        });
      }

      update();
    }

    window.initStickyReasoning = initStickyReasoning;
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initStickyReasoning);
    } else {
      initStickyReasoning();
    }
  })();
})();
