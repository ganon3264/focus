(function () {
  window._expandSets = window._expandSets || {};

  window.expandGet = function (setName, key) {
    window._expandSets[setName] = window._expandSets[setName] || new Set();
    return window._expandSets[setName].has(key);
  };

  window.expandToggle = function (setName, key) {
    window._expandSets[setName] = window._expandSets[setName] || new Set();
    var set = window._expandSets[setName];
    if (set.has(key)) {
      set.delete(key);
      return false;
    } else {
      set.add(key);
      return true;
    }
  };
})();
