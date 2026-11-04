(function () {
  window.countWords = function (text) {
    var trimmed = String(text || '').trim();
    return trimmed ? trimmed.split(/\s+/).length : 0;
  };

  window.wordCountLabel = function (text) {
    var n = window.countWords(text);
    if (!n) return '';
    return n.toLocaleString() + (n === 1 ? ' word' : ' words');
  };
})();
