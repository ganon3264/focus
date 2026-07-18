(function () {
  window.showErrorToast = function (message) {
    var toast = document.getElementById('error-toast');
    var textEl = document.getElementById('error-toast-text');
    if (!toast || !textEl) return;
    textEl.innerText = message;
    toast.classList.remove('hidden');
  };

  window.hideErrorToast = function () {
    var toast = document.getElementById('error-toast');
    if (toast) toast.classList.add('hidden');
  };
})();
