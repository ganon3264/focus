(function () {
  window.isClaudeProvider = function (provider) {
    return (
      provider &&
      provider.type === 'openrouter' &&
      provider.model &&
      provider.model.startsWith('anthropic/claude')
    );
  };

  window.updateClaudeCache = function (providerId, samplers) {
    if (samplers && samplers.cache_enabled) {
      localStorage.setItem('focus-cache-time-' + providerId, Date.now().toString());
      localStorage.setItem(
        'focus-cache-ttl-' + providerId,
        samplers.cache_ttl || 'ephemeral',
      );
    }
  };

  window.getClaudeCacheTimer = function (providerId) {
    var cacheTime = parseInt(localStorage.getItem('focus-cache-time-' + providerId), 10);
    var cacheTtl = localStorage.getItem('focus-cache-ttl-' + providerId) || 'ephemeral';
    if (!cacheTime) return null;
    var ttlMs = cacheTtl === '1h' ? 3600000 : 300000;
    var remaining = cacheTime + ttlMs - Date.now();
    if (remaining <= 0) return null;
    return remaining;
  };
})();
