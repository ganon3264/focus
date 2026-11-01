(function () {
  function apply() {
    if (new URLSearchParams(location.search).has('grid')) {
      document.body.classList.add('show-grid');
    }
  }
  window.toggleGrid = function () {
    document.body.classList.toggle('show-grid');
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', apply);
  } else {
    apply();
  }
})();
