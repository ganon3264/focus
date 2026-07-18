(function () {
  var pendingConfirmCallback = null;

  window.closeConfirmModal = function () {
    var el = document.getElementById('global-confirm-modal');
    if (el) el.classList.add('hidden');
    pendingConfirmCallback = null;
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
    var modal = document.getElementById('global-confirm-modal');
    if (modal) modal.classList.remove('hidden');
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
    e.preventDefault();
    var message = e.detail.question;
    if (!message) {
      e.detail.issueRequest(true);
      return;
    }
    window.openConfirmModal(message, function () {
      e.detail.issueRequest(true);
    });
  });
})();
