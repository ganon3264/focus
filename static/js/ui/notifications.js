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

  window.showInfoToast = function (message) {
    var toast = document.getElementById('info-toast');
    var textEl = document.getElementById('info-toast-text');
    if (!toast || !textEl) return;
    textEl.innerText = message;
    toast.classList.remove('hidden');
    clearTimeout(window._infoToastTimer);
    window._infoToastTimer = setTimeout(function () {
      toast.classList.add('hidden');
    }, 3000);
  };
})();
