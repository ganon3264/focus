// Single owner of the chat's scroll position: whether the reader is pinned to
// the bottom, and how the view follows a growing reply.
//
// Pinned-ness is one measurement of the scroller — the distance from the bottom
// — and pinning is its inverse, so the steady state is always "pinned" and
// nothing needs a tolerance band. Growth is the only signal: a token rendered, a
// reasoning block unfolded, a tool card opened, an image decoded, pruned rows
// re-inflated. All of them resize the list, so all of them land in onGrowth and
// no stream handler has to remember to scroll.
(function () {
  var SLACK = 1; // subpixel scroll jitter

  var scroller = null;
  var observer = null;
  var pinned = true;
  var landed = false; // the first layout pass owns the landing scroll

  function distance() {
    if (!scroller) return 0;
    return scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
  }

  function measure() {
    pinned = distance() <= SLACK;
  }

  function pin() {
    if (!scroller) return;
    if (typeof scroller.scrollTo === 'function') {
      scroller.scrollTo({ top: scroller.scrollHeight, behavior: 'instant' });
    } else {
      scroller.scrollTop = scroller.scrollHeight;
    }
    pinned = true;
  }

  // `always` chases the newest line even after the reader scrolled away;
  // `pinned` follows only while they are still at the bottom; `disabled` never
  // moves the view, whatever grows.
  function follows() {
    var mode = window.Prefs ? window.Prefs.get('follow_stream') : 'pinned';
    if (mode === 'always') return true;
    if (mode === 'disabled') return false;
    return pinned;
  }

  function onGrowth() {
    if (!landed) {
      landed = true;
      // A search hit owns the landing position: it scrolls itself after load.
      if (new URLSearchParams(window.location.search).get('at')) return measure();
      return pin();
    }
    if (follows()) pin();
    else measure();
  }

  window.ChatScroll = {
    // Idempotent — every render pass may call it.
    init: function () {
      var list = document.getElementById('message-list');
      var cc = document.querySelector('[data-ui="chat-center"]');
      if (!list || !cc || scroller === cc) return;
      scroller = cc;
      if (observer) observer.disconnect();
      observer = new ResizeObserver(onGrowth);
      observer.observe(list);
      // The reader's own scrolling: the measurement is synchronous, so a wheel
      // that leaves the bottom is recorded before the next growth can pin.
      cc.addEventListener('scroll', measure, { passive: true });
    },

    pin: pin,

    // The reader took over: keep the view where it is, whatever grows next.
    unpin: function () { pinned = false; },

    pinned: function () { return pinned; },

    distance: distance,
  };

  document.addEventListener('DOMContentLoaded', function () { window.ChatScroll.init(); });
})();
