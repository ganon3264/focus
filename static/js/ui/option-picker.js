// Shared option picker — powers #modal-select-option (OpenRouter route/quant,
// theme pickers, ...). Open with window.openOptionPicker(options, title, cb).
(function () {
  var _callback = null;

  window.openOptionPicker = function (options, title, callback) {
    var el = document.getElementById('modal-select-option');
    if (!el) return;
    try {
      var data = Alpine.$data(el);
      data.options = options || [];
      data.title = title || 'Select';
      data.search = '';
    } catch (e) {}
    _callback = callback || null;
    window.openModal('modal-select-option');
  };

  document.addEventListener('option-selected', function (e) {
    if (_callback) {
      var cb = _callback;
      _callback = null;
      cb(e.detail.value, e.detail.label);
    }
  });
})();
