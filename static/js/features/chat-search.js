// Chat search: a banded modal over every message hit, opened from the right
// pane's rail. The scope starts on the active character; the All chats chip
// widens it to every chat. A hit lands on its message via `?at=`.
(function () {
  var field = document.getElementById('chat-search-field');
  var lane = document.getElementById('chat-search-lane');
  if (!field || !lane) return;

  var readout = document.querySelector('[data-ui="search-readout"]');
  var idle = lane.innerHTML;
  var timer = null;
  var global = false;

  function searchUrl(query) {
    var url = window.api.partials.chatSearch + '?q=' + encodeURIComponent(query);
    var characterId = window.StateManager.get('character_id');
    if (!global && characterId) url += '&character_id=' + encodeURIComponent(characterId);
    return url;
  }

  function syncReadout() {
    if (!readout) return;
    var node = lane.querySelector('[data-search-count]');
    var n = node ? parseInt(node.getAttribute('data-search-count'), 10) || 0 : 0;
    if (!n) {
      readout.textContent = 'Messages';
      return;
    }
    var max = parseInt(node.getAttribute('data-search-max'), 10) || 0;
    readout.textContent = n + (max && n >= max ? '+' : '') + (n === 1 ? ' result' : ' results');
  }

  function reset() {
    lane.innerHTML = idle;
    syncReadout();
  }

  function run() {
    var query = field.value.trim();
    if (!query) {
      reset();
      return;
    }
    // The readout follows the swap, never the promise: hxGet resolves first.
    window.hxGet(searchUrl(query), { target: '#chat-search-lane', swap: 'innerHTML' })
      .catch(function (e) {
        window.showErrorToast(e.message || 'Search failed');
      });
  }

  document.addEventListener('htmx:afterSwap', function (e) {
    var target = e.detail && e.detail.target;
    if (!target || target.id !== 'chat-search-lane') return;
    syncReadout();
    // The lane is born after DOMContentLoaded, so its clocks have never been
    // localised; the formatter is the one owner of that conversion.
    if (window.formatTimestamps) window.formatTimestamps();
  });

  field.addEventListener('input', function () {
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () {
      timer = null;
      run();
    }, 180);
  });

  // Escape empties the query; a second one closes the modal through the shared
  // document handler, which this stopPropagation keeps out of the way.
  field.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape' || !field.value) return;
    e.stopPropagation();
    field.value = '';
    run();
  });

  window.actionToggleChatSearchScope = function (el) {
    global = !global;
    el.classList.toggle('active', global);
    el.setAttribute('aria-pressed', global ? 'true' : 'false');
    run();
  };

  window.actionOpenChatSearch = function () {
    window.openModal('modal-chat-search');
    field.focus();
    field.select();
  };

  if (window.ModalController) {
    ModalController.onOpen('modal-chat-search', function () {
      if (!field.value.trim()) reset();
    });
  }

  // Arriving from a hit: the initial scroll is ours, not the bottom of the chat.
  function land() {
    var at = new URLSearchParams(window.location.search).get('at');
    if (!at) return;
    var node = window.MessageIdentity ? MessageIdentity.node(at) : document.getElementById('message-' + at);
    if (!node) {
      // The scroll manager stood down for this URL, so a hit that is gone must
      // still put the view somewhere sensible.
      if (window.ChatScroll) window.ChatScroll.pin();
      return;
    }
    node.scrollIntoView({ block: 'center', behavior: 'instant' });
    node.classList.add('is-found');
    setTimeout(function () { node.classList.remove('is-found'); }, 1600);
  }

  document.addEventListener('DOMContentLoaded', land);
})();
