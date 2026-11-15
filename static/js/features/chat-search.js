// Chat search: the field at the foot of the right pane swaps the chat list for
// message hits, and a hit lands on its message via `?at=`.
(function () {
  var field = document.getElementById('chat-search-field');
  var lane = document.getElementById('chat-list');
  var pager = document.getElementById('chat-pager');
  if (!field || !lane) return;

  var timer = null;
  var restorePage = null;

  function listPage() {
    var scroll = lane.querySelector('[data-chat-page]');
    return scroll ? parseInt(scroll.getAttribute('data-chat-page'), 10) : 1;
  }

  function showResults(query) {
    if (restorePage === null) restorePage = listPage() || 1;
    if (pager) pager.classList.add('hidden');
    return window.hxGet(window.api.partials.chatSearch + '?q=' + encodeURIComponent(query), {
      target: '#chat-list',
      swap: 'innerHTML',
    }).catch(function (e) {
      window.showErrorToast(e.message || 'Search failed');
    });
  }

  function showList() {
    if (pager) pager.classList.remove('hidden');
    if (restorePage === null) return;
    var page = restorePage;
    restorePage = null;
    window._refreshChatList(window.StateManager.get('chat_id'), page);
  }

  field.addEventListener('input', function () {
    var query = field.value.trim();
    if (timer) clearTimeout(timer);
    timer = setTimeout(function () {
      timer = null;
      if (query) showResults(query);
      else showList();
    }, 180);
  });

  field.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (!field.value) return;
    e.stopPropagation();
    field.value = '';
    showList();
  });

  // Arriving from a hit: the initial scroll is ours, not the bottom of the chat.
  function land() {
    var at = new URLSearchParams(window.location.search).get('at');
    if (!at) return;
    var node = window.MessageIdentity ? MessageIdentity.node(at) : document.getElementById('message-' + at);
    if (!node) {
      // The scroll manager stood down for this URL, so a hit that is gone must
      // still put the view somewhere sensible.
      if (window.scrollSentinel) window.scrollSentinel.scrollIntoView({ block: 'end' });
      return;
    }
    node.scrollIntoView({ block: 'center', behavior: 'instant' });
    node.classList.add('is-found');
    setTimeout(function () { node.classList.remove('is-found'); }, 1600);
  }

  document.addEventListener('DOMContentLoaded', land);
})();
