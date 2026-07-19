(function () {
  var BUFFER = 1.0;
  var _pruned = new Map();
  var _rafId = null;

  function _getCC() {
    return document.querySelector('.chat-center');
  }

  function pruneMessages() {
    var cc = _getCC();
    var ml = document.getElementById('message-list');
    if (!cc || !ml) return;

    var vh = cc.clientHeight;
    if (vh < 100) return;
    var st = cc.scrollTop;
    var range = vh * BUFFER;
    var topBound = st - range;
    var botBound = st + vh + range;

    var streamId = window._streamingMessageId;

    var toPrune = [];
    var msgs = ml.querySelectorAll('.message');
    for (var i = 0; i < msgs.length; i++) {
      var msg = msgs[i];
      var id = msg.id;
      if (!id || _pruned.has(id) || id === streamId || id === 'streaming-message') continue;
      var rect = msg.getBoundingClientRect();
      var msgTop = rect.top + st;
      var msgBot = rect.bottom + st;
      if (msgBot < topBound || msgTop > botBound) {
        toPrune.push({ el: msg, id: id, height: msg.offsetHeight, html: msg.outerHTML });
      }
    }

    var toRestore = [];
    var phs = ml.querySelectorAll('.message-placeholder');
    for (var j = 0; j < phs.length; j++) {
      var ph = phs[j];
      var phId = ph.dataset.msgId;
      if (!phId) continue;
      var rect = ph.getBoundingClientRect();
      var phTop = rect.top + st;
      var phBot = rect.bottom + st;
      if (phBot >= topBound && phTop <= botBound) {
        var stored = _pruned.get(phId);
        if (stored) toRestore.push({ el: ph, id: phId, html: stored.html });
      }
    }

    for (var k = 0; k < toPrune.length; k++) {
      var p = toPrune[k];
      var ph = document.createElement('div');
      ph.className = 'message-placeholder';
      ph.dataset.msgId = p.id;
      ph.style.height = p.height + 'px';
      p.el.replaceWith(ph);
      _pruned.set(p.id, { html: p.html, height: p.height });
    }

    for (var l = 0; l < toRestore.length; l++) {
      var r = toRestore[l];
      var temp = document.createElement('div');
      temp.innerHTML = r.html;
      var msg = temp.firstElementChild;
      if (msg) {
        r.el.replaceWith(msg);
        if (typeof htmx !== 'undefined') htmx.process(msg);
        if (typeof syncReasoningButtons === 'function') {
          syncReasoningButtons(msg);
        }
      }
      _pruned.delete(r.id);
    }
    if (window.formatTimestamps) window.formatTimestamps();
  }

  function schedule() {
    if (_rafId) return;
    _rafId = requestAnimationFrame(function () {
      _rafId = null;
      pruneMessages();
    });
  }

  window._isMessagePruned = function (msgId) {
    return _pruned.has(msgId);
  };

  window._unpruneMessage = function (msgId) {
    var stored = _pruned.get(msgId);
    if (!stored) return null;

    var ph = document.querySelector('.message-placeholder[data-msg-id="' + msgId + '"]');
    if (!ph) {
      _pruned.delete(msgId);
      return null;
    }

    var temp = document.createElement('div');
    temp.innerHTML = stored.html;
    var msg = temp.firstElementChild;
    if (msg) {
      ph.replaceWith(msg);
      if (typeof htmx !== 'undefined') htmx.process(msg);
      if (typeof syncReasoningButtons === 'function') {
        syncReasoningButtons(msg);
      }
      _pruned.delete(msgId);
      return msg;
    }
      _pruned.delete(msgId);
      return null;
  };

  document.addEventListener('DOMContentLoaded', function () {
    var cc = _getCC();
    if (cc) {
      cc.addEventListener('scroll', schedule, { passive: true });
      setTimeout(function () {
        pruneMessages();
        window.addEventListener('load', pruneMessages);
      }, 150);
    }
  });

  document.addEventListener('htmx:beforeSwap', function (evt) {
    if (evt.detail.target && evt.detail.target.id === 'message-list') {
      _pruned.clear();
    }
  });

  document.addEventListener('htmx:afterSettle', function (evt) {
    if (evt.detail.target && evt.detail.target.closest('#message-list')) {
      schedule();
    }
  });

  window.pruneMessages = schedule;
})();
