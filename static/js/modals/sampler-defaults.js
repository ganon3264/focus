// Sampler defaults and effort options now come from window.PROVIDER_SCHEMA
// (embedded from focus/providers/schema.py) via ProviderSchema. These globals
// remain as thin delegates for existing call sites.
(function () {
  window.getSamplerDefaults = function (providerType) {
    return window.ProviderSchema.getSamplerDefaults(providerType);
  };

  window.getSamplerEffortOptions = function (providerType) {
    return window.ProviderSchema.getSamplerEffortOptions(providerType);
  };
})();
