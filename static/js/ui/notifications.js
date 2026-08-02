(function () {
  var MAX_VISIBLE = 5;
  var DEFAULT_DURATION = 3000;
  var EXIT_ANIMATION_MS = 220;
  var container = null;

  function getContainer() {
    if (!container) container = document.getElementById('toast-container');
    return container;
  }

  function getToastText(card) {
    var textEl = card.querySelector('.toast-text');
    return textEl ? textEl.textContent : '';
  }

  function clearTimer(card) {
    if (card._toastTimer) {
      clearTimeout(card._toastTimer);
      card._toastTimer = null;
    }
  }

  function armTimer(card, duration) {
    clearTimer(card);
    if (!duration || duration <= 0) return;
    card._remaining = duration;
    card._pausedAt = 0;
    card._toastTimer = setTimeout(function () {
      dismiss(card);
    }, duration);
  }

  function pauseTimer(card) {
    if (!card._toastTimer) return;
    clearTimer(card);
    card._pausedAt = Date.now();
  }

  function resumeTimer(card) {
    if (!card._pausedAt) return;
    var elapsed = Date.now() - card._pausedAt;
    card._pausedAt = 0;
    card._remaining = Math.max(0, card._remaining - elapsed);
    if (card._remaining > 0) {
      card._toastTimer = setTimeout(function () {
        dismiss(card);
      }, card._remaining);
    } else {
      dismiss(card);
    }
  }

  function dismiss(card) {
    if (card._dismissed) return;
    card._dismissed = true;
    clearTimer(card);
    if (card._onPause) {
      card.removeEventListener('mouseenter', card._onPause);
      card.removeEventListener('mouseleave', card._onResume);
    }
    card.classList.add('toast-leave');
    var remove = function () {
      card.remove();
    };
    card.addEventListener('animationend', remove);
    setTimeout(remove, EXIT_ANIMATION_MS);
  }

  window.showToast = function (message, opts) {
    opts = opts || {};
    var type = opts.type || 'info';
    var duration =
      opts.duration !== undefined ? opts.duration : type === 'error' ? 0 : DEFAULT_DURATION;
    var c = getContainer();
    if (!c || !message) return null;

    var children = c.children || [];
    for (var i = 0; i < children.length; i++) {
      var existing = children[i];
      if (existing._dismissed) continue;
      if (
        existing.dataset &&
        existing.dataset.toastType === type &&
        getToastText(existing) === message
      ) {
        armTimer(existing, duration);
        return existing;
      }
    }

    var card = document.createElement('div');
    card.className = 'toast toast-' + type;
    card.setAttribute('role', type === 'error' ? 'alert' : 'status');
    card.dataset.toastType = type;

    var text = document.createElement('span');
    text.className = 'toast-text';
    text.textContent = message;
    card.appendChild(text);

    if (type === 'error') {
      var actions = document.createElement('span');
      actions.className = 'toast-actions';
      var copyIcon = (window.getSvgSprite ? window.getSvgSprite('copy', 14) : '') || 'Copy';
      var copy = document.createElement('button');
      copy.className = 'toast-btn';
      copy.setAttribute('aria-label', 'Copy error');
      copy.innerHTML = copyIcon;
      copy.addEventListener('click', function () {
        var txt = text.textContent;
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(txt).then(
            function () {
              copy.innerHTML = 'Copied!';
              setTimeout(function () {
                copy.innerHTML = copyIcon;
              }, 1500);
            },
            function () {
              _fallbackCopy(txt);
            },
          );
        } else {
          _fallbackCopy(txt);
        }
      });
      var close = document.createElement('button');
      close.className = 'toast-btn toast-close';
      close.setAttribute('aria-label', 'Dismiss');
      close.innerHTML = (window.getSvgSprite ? window.getSvgSprite('close', 14) : '') || '×';
      close.addEventListener('click', function () {
        dismiss(card);
      });
      actions.appendChild(copy);
      actions.appendChild(close);
      card.appendChild(actions);
    }

    c.appendChild(card);

    var activeCount = 0;
    for (var j = 0; j < c.children.length; j++) {
      if (!c.children[j]._dismissed) activeCount++;
    }
    for (var k = 0; k < c.children.length && activeCount > MAX_VISIBLE; k++) {
      if (!c.children[k]._dismissed) {
        dismiss(c.children[k]);
        activeCount--;
      }
    }

    if (duration > 0) {
      armTimer(card, duration);
      card._onPause = function () {
        pauseTimer(card);
      };
      card._onResume = function () {
        resumeTimer(card);
      };
      card.addEventListener('mouseenter', card._onPause);
      card.addEventListener('mouseleave', card._onResume);
    }

    return card;
  };

  function _fallbackCopy(text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand('copy');
    } catch (e) {}
    document.body.removeChild(ta);
  }

  window.showInfoToast = function (message, opts) {
    opts = opts || {};
    opts.type = 'info';
    window.showToast(message, opts);
  };

  window.showSuccessToast = function (message, opts) {
    opts = opts || {};
    opts.type = 'success';
    window.showToast(message, opts);
  };

  window.showErrorToast = function (message, opts) {
    opts = opts || {};
    opts.type = 'error';
    window.showToast(message, opts);
  };

  function dismissCards(predicate) {
    var c = getContainer();
    if (!c) return;
    Array.prototype.slice.call(c.children || []).forEach(function (card) {
      if (!predicate || predicate(card)) dismiss(card);
    });
  }

  window.hideErrorToast = function () {
    dismissCards(function (card) {
      return card.dataset && card.dataset.toastType === 'error';
    });
  };

  window.hideAllToasts = function () {
    dismissCards();
  };

  window.showImportToast = function (data, pluralLabel) {
    var imported = (data && data.imported && data.imported.length) || 0;
    var total = (data && data.total) || 0;
    if (data && data.errors && data.errors.length) {
      window.showErrorToast(
        'Imported ' +
          imported +
          ' of ' +
          total +
          ' cards.\n\nErrors:\n' +
          data.errors
            .map(function (e) {
              return '\u2022 ' + e.filename + ': ' + e.error;
            })
            .join('\n'),
      );
    } else {
      window.showSuccessToast('Imported ' + imported + ' ' + pluralLabel);
    }
  };
})();
