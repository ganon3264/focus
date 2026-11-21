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

  // One draft per chat, kept out of the DB: a half-written reply must survive a
  // reload or a hop to another chat. The composer is the only thing that owns
  // it, the same way the input bar is the only thing that owns the field.
  var DRAFT_PREFIX = 'focus-draft-';
  var draftTimer = null;
  var draftKeyPending = null;

  function draftKey() {
    var chatId = window.StateManager ? window.StateManager.get('chat_id') : null;
    return chatId ? DRAFT_PREFIX + chatId : null;
  }

  function writeDraft(key) {
    if (!key) return;
    try {
      if (input.value.trim()) window.localStorage.setItem(key, input.value);
      else window.localStorage.removeItem(key);
    } catch (e) {
      // storage disabled or full: the composer still works, it just forgets.
    }
  }

  // The key is captured when the save is scheduled, not when the timer fires:
  // a chat switch landing inside the debounce window must not file this chat's
  // text under the next chat's id.
  function saveDraft() {
    if (draftTimer) clearTimeout(draftTimer);
    draftKeyPending = draftKey();
    draftTimer = setTimeout(function () {
      draftTimer = null;
      writeDraft(draftKeyPending);
      draftKeyPending = null;
    }, 250);
  }

  // A pending debounce dies with the page, so leaving it flushes now. Same
  // value, no truncation: the write is one snapshot of the whole composer.
  function flushDraft() {
    if (!draftTimer) return;
    clearTimeout(draftTimer);
    draftTimer = null;
    writeDraft(draftKeyPending);
    draftKeyPending = null;
  }

  window.clearComposerDraft = function () {
    if (draftTimer) {
      clearTimeout(draftTimer);
      draftTimer = null;
    }
    draftKeyPending = null;
    var key = draftKey();
    if (!key) return;
    try {
      window.localStorage.removeItem(key);
    } catch (e) {
      // nothing to clear if storage is unavailable
    }
  };

  // Whoever wrote the text — us, or the browser restoring form state on reload
  // after this hook has already run — the box has to be measured against it.
  function syncComposer() {
    if (!input) return;
    resizeTextarea(input);
    updateSendButtonState();
  }

  // A saved draft is the newest thing the user typed, so it wins over whatever
  // the browser kept from the last session. No draft means the field is left
  // alone and only measured.
  function restoreDraft() {
    var key = draftKey();
    var saved = null;
    if (key) {
      try {
        saved = window.localStorage.getItem(key);
      } catch (e) {
        saved = null;
      }
    }
    if (saved) input.value = saved;
    syncComposer();
  }

  if (input) {
    input.addEventListener('input', function () {
      resizeTextarea(this);
      updateSendButtonState();
      saveDraft();
    });
    input.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      var mode = window.Prefs ? window.Prefs.get('send_key') : 'enter';
      var withMod = e.ctrlKey || e.metaKey;
      var sends = mode === 'ctrl_enter' ? withMod : !e.shiftKey && !withMod;
      if (!sends) return;
      if (sendBtn && !sendBtn.classList.contains('hidden')) {
        e.preventDefault();
        sendBtn.click();
      }
    });
  }

  if (sendBtn) {
    updateSendButtonState();
  }

  // StateManager is initialised by the page script, which runs during parsing
  // but after this module.
  document.addEventListener('DOMContentLoaded', restoreDraft);
  // Firefox applies its own form-state restoration after DOMContentLoaded and
  // does not fire an input event, so the composer is measured again once the
  // page has settled and again when a bfcache navigation brings it back.
  window.addEventListener('load', syncComposer);
  window.addEventListener('pageshow', syncComposer);

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'hidden') flushDraft();
  });
  window.addEventListener('pagehide', flushDraft);
})();
