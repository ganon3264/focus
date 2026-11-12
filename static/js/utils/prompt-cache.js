// Ephemeral prompt caching. The model families that accept cache_control
// breakpoints are declared by the provider profile (window.PROVIDER_SCHEMA), and
// the fixed-TTL families by the schema itself, so the sampler, the status panel
// and the generation lifecycle share one predicate.
(function () {
  function capabilities(provider) {
    return (window.ProviderSchema && ProviderSchema.capabilities(provider.type)) || {};
  }

  function matches(provider, prefixes) {
    return !!provider && !!provider.model && (prefixes || []).some(function (prefix) {
      return provider.model.indexOf(prefix) === 0;
    });
  }

  window.usesEphemeralCache = function (provider) {
    return !!provider && matches(provider, capabilities(provider).cache_breakpoint_models);
  };

  // Gemini's ephemeral cache has a fixed upstream TTL, so the extra-hour
  // sampler never reaches it.
  window.canExtendCacheTtl = function (provider) {
    var fixed = window.PROVIDER_SCHEMA && window.PROVIDER_SCHEMA.fixedCacheTtlModels;
    return !matches(provider, fixed);
  };

  window.updatePromptCache = function (provider, samplers) {
    if (!provider || !samplers || !samplers.cache_enabled) return;
    localStorage.setItem('focus-cache-time-' + provider.id, Date.now().toString());
    localStorage.setItem(
      'focus-cache-ttl-' + provider.id,
      window.canExtendCacheTtl(provider) ? samplers.cache_ttl || 'ephemeral' : 'ephemeral',
    );
  };

  window.getPromptCacheTimer = function (providerId) {
    var cacheTime = parseInt(localStorage.getItem('focus-cache-time-' + providerId), 10);
    var cacheTtl = localStorage.getItem('focus-cache-ttl-' + providerId) || 'ephemeral';
    if (!cacheTime) return null;
    var ttlMs = cacheTtl === '1h' ? 3600000 : 300000;
    var remaining = cacheTime + ttlMs - Date.now();
    return remaining > 0 ? remaining : null;
  };
})();
