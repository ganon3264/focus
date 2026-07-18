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

    var messages = ml.querySelectorAll('.message');
    messages.forEach(function (msg) {
      var id = msg.id;
      if (!id) return;
      if (_pruned.has(id)) return;

      var rect = msg.getBoundingClientRect();
      var msgTop = rect.top + st;
      var msgBot = rect.bottom + st;

      if (msgBot < topBound || msgTop > botBound) {
        var height = msg.offsetHeight;
        var html = msg.outerHTML;

        var ph = document.createElement('div');
        ph.className = 'message-placeholder';
        ph.dataset.msgId = id;
        ph.style.height = height + 'px';

        msg.replaceWith(ph);
        _pruned.set(id, { html: html, height: height });
      }
    });

    var placeholders = ml.querySelectorAll('.message-placeholder');
    placeholders.forEach(function (ph) {
      var id = ph.dataset.msgId;
      if (!id) return;

      var rect = ph.getBoundingClientRect();
      var phTop = rect.top + st;
      var phBot = rect.bottom + st;

      if (phBot >= topBound && phTop <= botBound) {
        var stored = _pruned.get(id);
        if (!stored) return;

        var temp = document.createElement('div');
        temp.innerHTML = stored.html;
        var msg = temp.firstElementChild;
        if (msg) {
          ph.replaceWith(msg);
          if (typeof htmx !== 'undefined') htmx.process(msg);
        }
        _pruned.delete(id);
      }
    });
  }

  function schedule() {
    if (_rafId) return;
    _rafId = requestAnimationFrame(function () {
      _rafId = null;
      pruneMessages();
    });
  }

  window._findMessageOrPlaceholder = function (msgId) {
    var el = document.getElementById('message-' + msgId);
    if (el) return el;
    return document.querySelector('.message-placeholder[data-msg-id="' + msgId + '"]');
  };

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
      _pruned.delete(msgId);
      return msg;
    }
    _pruned.delete(msgId);
    return null;
  };

  window._prunedCount = function () { return _pruned.size; };
  window._prunedIds = function () { return Array.from(_pruned.keys()); };

  window._clearPrunedCache = function () {
    _pruned.clear();
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
