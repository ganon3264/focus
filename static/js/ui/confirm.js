(function () {
  var CONFIRM_ID = 'global-confirm-modal';
  var pendingConfirmCallback = null;

  window.closeConfirmModal = function () {
    pendingConfirmCallback = null;
    if (!window.ModalController.isOpen(CONFIRM_ID)) return;
    window.ModalController.close(CONFIRM_ID, { discard: true });
  };

  window.openConfirmModal = function (message, callback) {
    var msgEl = document.getElementById('global-confirm-message');
    if (!msgEl) return;
    if (message && message.indexOf('<') !== -1) {
      msgEl.innerHTML = message;
    } else {
      msgEl.textContent = message || 'Are you sure?';
    }
    pendingConfirmCallback = callback;
    window.ModalController.open(CONFIRM_ID);
  };

  window.customConfirm = function (message, callback) {
    window.openConfirmModal(message, callback);
  };

  var confirmBtn = document.getElementById('global-confirm-btn');
  if (confirmBtn) {
    confirmBtn.addEventListener('click', function () {
      if (pendingConfirmCallback) {
        pendingConfirmCallback();
      }
      window.closeConfirmModal();
    });
  }

  document.addEventListener('htmx:confirm', function (e) {
    var message = e.detail.question;
    // No question means htmx would issue the request on its own; preventing the
    // default would resolve its promise without sending anything, and the
    // re-entrant issueRequest then races htmx's per-source "last wins" queue
    // (a queued reload is silently dropped).
    if (!message) return;
    e.preventDefault();
    window.openConfirmModal(message, function () {
      e.detail.issueRequest(true);
    });
  });
})();
