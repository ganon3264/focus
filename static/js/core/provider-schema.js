// Consumer of window.PROVIDER_SCHEMA (embedded server-side from
// focus/providers/schema.py). Owns sampler defaults, effort options, and the
// upstream forwarding whitelist so provider types no longer each hand-roll a
// build() function.
(function () {
  function schema() {
    return (window.PROVIDER_SCHEMA && window.PROVIDER_SCHEMA.types) || {};
  }

  function typeSchema(providerType) {
    return schema()[providerType] || {};
  }

  function getSamplerDefaults(providerType) {
    var base = (window.PROVIDER_SCHEMA && window.PROVIDER_SCHEMA.baseDefaults) || {};
    return Object.assign({}, base, typeSchema(providerType).defaults || {});
  }

  function getSamplerEffortOptions(providerType) {
    var ts = typeSchema(providerType);
    if (ts.effortOptions) return ts.effortOptions;
    return typeSchema('openai_compat').effortOptions || [];
  }

  function supported(providerType, key, supportedParams) {
    var filtered = typeSchema(providerType).capabilityFiltered || [];
    if (!supportedParams || filtered.indexOf(key) === -1) return true;
    return supportedParams.indexOf(key) !== -1;
  }

  function buildSamplers(providerType, samplers, supportedParams) {
    var ts = typeSchema(providerType);
    var out = {};
    (ts.forwardAlways || []).forEach(function (key) {
      if (supported(providerType, key, supportedParams)) out[key] = samplers[key];
    });
    if (samplers.include_reasoning) {
      (ts.forwardReasoning || []).forEach(function (key) {
        if (supported(providerType, key, supportedParams)) out[key] = samplers[key];
      });
    }
    // Value guards from the legacy per-provider builders: -1 means "random"
    // seed and must be omitted; empty verbosity is dropped so JSON.stringify
    // does not send it.
    if ('seed' in out && !(out.seed >= 0)) delete out.seed;
    if ('verbosity' in out && !out.verbosity) delete out.verbosity;
    return out;
  }

  function capabilities(providerType) {
    return typeSchema(providerType).capabilities || {};
  }

  var DEFAULT_FORM = {
    orFields: false, modelInput: true, baseUrl: true,
    vertexFields: false, modelRequired: true,
  };

  function formConfig(providerType) {
    return typeSchema(providerType).form || DEFAULT_FORM;
  }

  function fieldVisible(providerType, key) {
    return (typeSchema(providerType).visible || []).indexOf(key) !== -1;
  }

  // A field is usable when the type exposes it and the selected model accepts
  // it. ``supportedParams`` is null when capabilities are unknown (don't hide).
  function fieldSupported(providerType, key, supportedParams) {
    return fieldVisible(providerType, key) && supported(providerType, key, supportedParams);
  }

  window.ProviderSchema = {
    getSamplerDefaults: getSamplerDefaults,
    getSamplerEffortOptions: getSamplerEffortOptions,
    buildSamplers: buildSamplers,
    capabilities: capabilities,
    formConfig: formConfig,
    fieldVisible: fieldVisible,
    fieldSupported: fieldSupported,
  };
})();
