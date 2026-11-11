function toggleProviderFields(prefix) {
  var type = document.getElementById(prefix + '-type').value;
  var orFields = document.getElementById(prefix + '-or-fields');
  var ngFields = document.getElementById(prefix + '-ng-fields');
  var modelInput = document.getElementById(prefix + '-model-input');
  var baseUrl = document.getElementById(prefix + '-baseurl');
  var vertexFields = document.getElementById(prefix + '-vertex-fields');

  var cfg = ProviderSchema.formConfig(type);

  if (orFields) {
    orFields.classList.toggle('hidden', !cfg.orFields);
    orFields.classList.toggle('flex', cfg.orFields);
  }
  if (ngFields) {
    ngFields.classList.toggle('hidden', !cfg.ngFields);
    ngFields.classList.toggle('flex', !!cfg.ngFields);
  }
  if (modelInput) {
    modelInput.classList.toggle('hidden', !cfg.modelInput);
    if (cfg.modelRequired) {
      modelInput.querySelector('input').setAttribute('required', 'required');
    } else {
      modelInput.querySelector('input').removeAttribute('required');
    }
  }
  if (baseUrl) baseUrl.classList.toggle('hidden', !cfg.baseUrl);
  if (vertexFields) {
    vertexFields.classList.toggle('hidden', !cfg.vertexFields);
    vertexFields.classList.toggle('flex', cfg.vertexFields);
  }

  const keyDisplay = document.getElementById('api-key-display-' + prefix);
  if (keyDisplay && keyDisplay.innerText.includes('Select')) {
    if (type === 'google_vertex') {
      keyDisplay.innerHTML = '<span class="text-muted">Select Service Account JSON...</span>';
    } else {
      keyDisplay.innerHTML = '<span class="text-muted">Select API Key...</span>';
    }
  }
}

window._currentFetchPrefix = null;

function openFetchModelModal(prefix) {
  window._currentFetchPrefix = prefix;
  openModal('modal-fetch-models');
  forceFetchModels();
}

async function forceFetchModels() {
  const prefix = window._currentFetchPrefix;
  if (!prefix) return;

  window.dispatchEvent(new CustomEvent('models-loading'));

  const type = document.getElementById(prefix + '-type')?.value;

  const baseUrlInput = document.getElementById(prefix + '-base-url');
  const baseUrl = baseUrlInput ? baseUrlInput.value : '';

  const apiKeyInput = document.getElementById('api-key-input-' + prefix);
  let apiKey = apiKeyInput ? apiKeyInput.value : '';

  let config = {};
  if (type === 'google_vertex') {
    const regionInput = document.getElementById(prefix + '-vertex-region');
    const projectInput = document.getElementById(prefix + '-vertex-project-id');
    if (regionInput) config.vertex_region = regionInput.value;
    if (projectInput) config.vertex_project_id = projectInput.value;
  }

  const editIdInput = document.getElementById('prov-form-edit-id');
  const providerId = editIdInput ? editIdInput.value : '';

  try {
    let body = { type, base_url: baseUrl, api_key: apiKey, params: {}, config };
    if (providerId) body.provider_id = providerId;

    const res = await hxJson(api.providerFetchModels, 'POST', body);

    if (!res.ok) {
      const errData = await res.json();
      throw new Error(errData.detail || 'Failed to fetch models from provider.');
    }

    const data = await res.json();
    window.dispatchEvent(new CustomEvent('models-loaded', { detail: data.data }));
  } catch (err) {
    console.error(err);
    window.dispatchEvent(new CustomEvent('models-error', { detail: err.message }));
  }
}
window.forceFetchModels = forceFetchModels;

function selectFetchedModel(id, name) {
  const prefix = window._currentFetchPrefix;
  if (!prefix) return;

  const type = document.getElementById(prefix + '-type')?.value;

  const input = document.getElementById('model-text-' + prefix);
  if (input) input.value = id;
  window.ModalController.refresh('modal-provider-create');
  if (type === 'openrouter') {
    fetchOROptions(id);
  } else if (type === 'nanogpt') {
    fetchNGRouteOptions(id);
  }

  closeModal('modal-fetch-models');
}

var _orRouteOptions = [{ value: '', label: 'Auto (Any)' }];
var _orQuantOptions = [{ value: '', label: 'Any' }];
var _orServiceTierOptions = [
  { value: '', label: 'Default (standard)' },
  { value: 'flex', label: 'Flex (cheaper, slower)' },
  { value: 'priority', label: 'Priority (faster, pricier)' },
  { value: 'ultrafast', label: 'Ultrafast (highest cost)' },
];

function _orServiceTierLabel(value) {
  for (var i = 0; i < _orServiceTierOptions.length; i++) {
    if (_orServiceTierOptions[i].value === (value || '')) return _orServiceTierOptions[i].label;
  }
  return _orServiceTierOptions[0].label;
}

function fetchOROptions(modelId) {
  if (!modelId) { _orRouteOptions = [{ value: '', label: 'Auto (Any)' }]; _orQuantOptions = [{ value: '', label: 'Any' }]; return; }
  hxFetch('/api/providers/openrouter/endpoints/' + encodeURIComponent(modelId))
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var endpoints = (data.data && data.data.endpoints) || [];
      var providerSet = {};
      endpoints.forEach(function (ep) { if (ep.provider_name) providerSet[ep.provider_name] = true; });
      var routeOpts = Object.keys(providerSet).sort();
      _orRouteOptions = [{ value: '', label: 'Auto (Any)' }];
      routeOpts.forEach(function (p) { _orRouteOptions.push({ value: p, label: p }); });
      var quantSet = {};
      endpoints.forEach(function (ep) { if (ep.quantization && ep.quantization !== 'unknown') quantSet[ep.quantization] = true; });
      var quantOpts = Object.keys(quantSet).sort();
      _orQuantOptions = [{ value: '', label: 'Any' }];
      quantOpts.forEach(function (q) { _orQuantOptions.push({ value: q, label: q }); });
    });
}

function openRouteSelectModal(prefix) {
  window.openOptionPicker(
    _orRouteOptions,
    'Select Provider Routing',
    function (value, label) {
      document.getElementById(prefix + '-or-route').value = value;
      document.getElementById('or-route-display-' + prefix).textContent = label;
      document.getElementById('or-route-display-' + prefix).classList.toggle('text-muted', !value);
      document.getElementById(prefix + '-or-route').dispatchEvent(new Event('change', { bubbles: true }));
      refreshNoFallbacksVisibility(prefix);
    },
  );
}

function openQuantSelectModal(prefix) {
  window.openOptionPicker(
    _orQuantOptions,
    'Select Quantization',
    function (value, label) {
      document.getElementById(prefix + '-or-quant').value = value;
      document.getElementById('or-quant-display-' + prefix).textContent = label;
      document.getElementById('or-quant-display-' + prefix).classList.toggle('text-muted', !value);
      document.getElementById(prefix + '-or-quant').dispatchEvent(new Event('change', { bubbles: true }));
    },
  );
}

function openServiceTierSelectModal(prefix) {
  window.openOptionPicker(
    _orServiceTierOptions,
    'Select Service Tier',
    function (value, label) {
      document.getElementById(prefix + '-or-service-tier').value = value;
      document.getElementById('or-service-tier-display-' + prefix).textContent = label;
      document.getElementById('or-service-tier-display-' + prefix).classList.toggle('text-muted', !value);
      document.getElementById(prefix + '-or-service-tier').dispatchEvent(new Event('change', { bubbles: true }));
    },
  );
}

function toggleNoFallbacks(prefix) {
  const toggle = document.getElementById(prefix + '-or-no-fallbacks-toggle');
  const input = document.getElementById(prefix + '-or-no-fallbacks');
  if (!toggle || !input) return;
  toggle.classList.toggle('active');
  input.value = toggle.classList.contains('active') ? 'true' : 'false';
  window.ModalController.refresh('modal-provider-create');
}

// Routable hosts come from NanoGPT's per-model provider discovery, so the list
// is empty until a model is chosen.
var _ngRouteOptions = [{ value: '', label: 'Auto (Any)' }];

function fetchNGRouteOptions(modelId) {
  if (!modelId) { _ngRouteOptions = [{ value: '', label: 'Auto (Any)' }]; return; }
  hxFetch(api.providerNanoGPTProviders(modelId))
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var hosts = Array.isArray(data.data) ? data.data : [];
      _ngRouteOptions = [{ value: '', label: 'Auto (Any)' }].concat(hosts);
    })
    .catch(function (err) {
      console.error(err);
      _ngRouteOptions = [{ value: '', label: 'Auto (Any)' }];
    });
}

function openNgRouteSelectModal(prefix) {
  window.openOptionPicker(
    _ngRouteOptions,
    'Select Provider Routing',
    function (value, label) {
      document.getElementById(prefix + '-ng-route').value = value;
      var display = document.getElementById('ng-route-display-' + prefix);
      display.textContent = label;
      display.classList.toggle('text-muted', !value);
      document.getElementById(prefix + '-ng-route').dispatchEvent(new Event('change', { bubbles: true }));
    },
  );
}

function refreshNoFallbacksVisibility(prefix) {
  const routeInput = document.getElementById(prefix + '-or-route');
  const row = document.getElementById(prefix + '-or-no-fallbacks-row');
  if (!routeInput || !row) return;
  row.classList.toggle('hidden', !routeInput.value);
}

function setActiveProvider(id, name, type) {
  window.applyProvider(id, type, name);
}

var RETRY_DEFAULTS = {
  enabled: true,
  max_retries: 5,
  base_delay: 2,
  max_delay: 20,
  on_rate_limit: false,
  on_server_error: true,
  on_timeout: true,
};

function parseStatusCodes(raw) {
  var values = [];
  var dropped = [];
  (raw || '').split(/[,\s]+/).forEach(function (tok) {
    if (!tok) return;
    var n = parseInt(tok, 10);
    if (String(n) === tok && n >= 100 && n <= 599) {
      if (values.indexOf(n) === -1) values.push(n);
    } else {
      dropped.push(tok);
    }
  });
  values.sort(function (a, b) { return a - b; });
  return { values: values, dropped: dropped };
}

function collectRetryConfig(form) {
  var codes = parseStatusCodes((form.querySelector('[name="retry_extra_statuses"]') || {}).value || '');
  var enabledEl = form.querySelector('[name="retry_enabled"]');
  var maxEl = form.querySelector('[name="retry_max_retries"]');
  var baseEl = form.querySelector('[name="retry_base_delay"]');
  var maxDelayEl = form.querySelector('[name="retry_max_delay"]');
  var rateEl = form.querySelector('[name="retry_rate_limit"]');
  var serverEl = form.querySelector('[name="retry_server_error"]');
  var timeoutEl = form.querySelector('[name="retry_timeout"]');

  function num(el, fallback) {
    var v = el ? parseFloat(el.value) : NaN;
    return isNaN(v) ? fallback : v;
  }

  return {
    config: {
      enabled: enabledEl ? enabledEl.value === 'true' : RETRY_DEFAULTS.enabled,
      max_retries: Math.max(0, Math.min(10, Math.round(num(maxEl, RETRY_DEFAULTS.max_retries)))),
      base_delay: num(baseEl, RETRY_DEFAULTS.base_delay),
      max_delay: num(maxDelayEl, RETRY_DEFAULTS.max_delay),
      on_rate_limit: rateEl ? !!rateEl.checked : RETRY_DEFAULTS.on_rate_limit,
      on_server_error: serverEl ? !!serverEl.checked : RETRY_DEFAULTS.on_server_error,
      on_timeout: timeoutEl ? !!timeoutEl.checked : RETRY_DEFAULTS.on_timeout,
      extra_statuses: codes.values,
    },
    dropped: codes.dropped,
  };
}

function extractData(form) {
  const data = Object.fromEntries(new FormData(form));
  if (data.api_key === '__HIDDEN__' || data.api_key === '') delete data.api_key;

  const type = data.type || form.querySelector('input[name="type"]').value;

  // params_json is upstream-only sampler defaults.
  try {
    data.params = JSON.parse(data.params || '{}');
  } catch (e) {
    data.params = {};
  }
  if (!data.params || typeof data.params !== 'object') data.params = {};

  // config_json is Focus-only provider settings; never sent upstream.
  let config = {};
  try {
    config = JSON.parse(data.config || '{}');
  } catch (e) {}
  if (!config || typeof config !== 'object') config = {};

  if (type === 'openrouter') {
    if (!data.model) {
      window.showErrorToast('Please select an OpenRouter model.', { duration: 4000 });
      throw new Error('Model required');
    }
    data.base_url = 'https://openrouter.ai/api/v1';

    if (data.or_route) config.or_route = data.or_route;
    else delete config.or_route;

    if (data.or_quant) config.or_quant = data.or_quant;
    else delete config.or_quant;

    if (data.or_service_tier) config.or_service_tier = data.or_service_tier;
    else delete config.or_service_tier;

    const orNoFallbacksInput = form.querySelector('[name="or_no_fallbacks"]');
    config.or_no_fallbacks = orNoFallbacksInput ? orNoFallbacksInput.value === 'true' : true;
  } else if (type === 'nanogpt') {
    if (!data.model) {
      window.showErrorToast('Please select a NanoGPT model.', { duration: 4000 });
      throw new Error('Model required');
    }
    data.base_url = 'https://api.nano-gpt.com/api/v1';

    if (data.ng_route) config.ng_route = data.ng_route;
    else delete config.ng_route;
  } else if (type === 'google_vertex') {
    if (data.vertex_region) config.vertex_region = data.vertex_region;
    if (data.vertex_project_id) config.vertex_project_id = data.vertex_project_id;
    data.base_url = '';
  } else if (type === 'google_aistudio' || type === 'deepseek' || type === 'moonshot') {
    delete data.base_url;
  }

  var apiKeys = [];
  try {
    apiKeys = JSON.parse(data.api_keys_json || '[]');
  } catch (e) {}
  apiKeys = Array.isArray(apiKeys)
    ? apiKeys.filter(function (k) { return typeof k === 'string' && k; })
    : [];
  if (apiKeys.length) {
    config.api_keys = apiKeys;
    data.api_key = apiKeys[0];
  } else {
    delete config.api_keys;
  }
  delete data.api_keys_json;

  var retryResult = collectRetryConfig(form);
  config.retry = retryResult.config;
  data.config = config;
  if (retryResult.dropped.length && window.showInfoToast) {
    window.showInfoToast('Ignored invalid retry status code(s): ' + retryResult.dropped.join(', '), { duration: 4000 });
  }

  delete data.or_route;
  delete data.or_quant;
  delete data.or_service_tier;
  delete data.or_no_fallbacks;
  delete data.ng_route;
  delete data.vertex_region;
  delete data.vertex_project_id;
  delete data.retry_enabled;
  delete data.retry_max_retries;
  delete data.retry_base_delay;
  delete data.retry_max_delay;
  delete data.retry_rate_limit;
  delete data.retry_server_error;
  delete data.retry_timeout;
  delete data.retry_extra_statuses;

  return data;
}

function submitProviderForm(el, e) {
  e.preventDefault();
  const form = window.resolveFormFromEvent(e);
  if (!form) return;
  let data;
  try {
    data = extractData(form);
  } catch (err) {
    return;
  }
  const editId = document.getElementById('prov-form-edit-id').value;
  const isEdit = !!editId;
  const url = isEdit ? api.provider(editId) : api.providers;
  const method = isEdit ? 'PATCH' : 'POST';
  hxJson(url, method, data).then(async function (r) {
    if (r.ok) {
      closeModal('modal-provider-create', { discard: true });
      // Refresh the store before the new card is clickable, so selecting it can
      // never read a stale/absent record.
      var storeReady = window.ProviderStore ? ProviderStore.refresh() : Promise.resolve();
      storeReady.finally(function () {
        hxGet(api.partials.providersModal, {
          target: '#providers-modal-body-inner',
          swap: 'innerHTML',
        });
      });
      window.showSuccessToast(isEdit ? 'Provider updated' : 'Provider added');
    } else {
      var errBody;
      try { errBody = await r.json(); } catch (e) { errBody = await r.text(); }
      console.error('Provider save failed:', r.status, errBody);
      var detail = errBody && (errBody.detail || errBody.message);
      window.showErrorToast('Could not save provider — ' + (detail || 'HTTP ' + r.status));
    }
  });
}

window.openProviderEditModal = async function (id) {
  resetProviderForm();
  try {
    const res = await hxFetch(api.provider(id));
    if (!res.ok) return;
    const data = await res.json();
    populateProviderForm(data);
    document.getElementById('prov-form-edit-id').value = id;
    var submitBtn = document.getElementById('prov-form-submit-btn');
    submitBtn.textContent = 'Save Provider';
    submitBtn.className = 'btn primary ml-auto';
    var titleEl = document.querySelector('#modal-provider-create [data-ui="modal-title"]');
    if (titleEl) titleEl.textContent = 'Edit ' + (data.name || 'Provider');
    openModal('modal-provider-create');
  } catch (err) {
    console.error(err);
  }
};

window.openProviderCreateModal = function () {
  resetProviderForm();
  document.getElementById('prov-form-edit-id').value = '';
  var submitBtn = document.getElementById('prov-form-submit-btn');
  submitBtn.textContent = 'Add Provider';
  submitBtn.className = 'btn create ml-auto';
  var titleEl = document.querySelector('#modal-provider-create [data-ui="modal-title"]');
  if (titleEl) titleEl.textContent = 'New Provider';
  openModal('modal-provider-create');
};

function setSelectValue(inputId, value) {
  var input = document.getElementById(inputId);
  if (!input) return;
  input.value = value;
  var container = input.closest('[x-data]');
  if (container) {
    var label = value;
    var opt = container.querySelector('[data-value="' + value.replace(/"/g, '\\"') + '"]');
    if (opt) label = opt.textContent.trim();
    container.dispatchEvent(new CustomEvent('custom-select:set', {
      detail: { value: value, label: label },
      bubbles: true,
    }));
  }
};

function setInputValue(id, value) {
  var el = document.getElementById(id);
  if (el) el.value = value;
}

function setInputChecked(id, value) {
  var el = document.getElementById(id);
  if (el) el.checked = !!value;
}

function openRetryModal() {
  openModal('modal-provider-retry');
  refreshRetryHint();
}

function toggleRetryEnabled(prefix) {
  var toggle = document.getElementById(prefix + '-retry-toggle');
  var input = document.getElementById(prefix + '-retry-enabled');
  if (!toggle || !input) return;
  toggle.classList.toggle('active');
  input.value = toggle.classList.contains('active') ? 'true' : 'false';
  window.ModalController.refresh('modal-provider-create');
  refreshRetryHint();
}

function refreshRetryHint() {
  var hint = document.getElementById('prov-form-retry-hint');
  var enabled = document.getElementById('prov-form-retry-enabled');
  refreshRetrySummary();
  if (!hint || !enabled) return;
  var anyClass = ['prov-form-retry-rate', 'prov-form-retry-server', 'prov-form-retry-timeout'].some(function (id) {
    var el = document.getElementById(id);
    return el && el.checked;
  });
  var extra = document.getElementById('prov-form-retry-extra');
  var hasCodes = extra ? parseStatusCodes(extra.value).values.length > 0 : false;
  var inactive = enabled.value === 'true' && !anyClass && !hasCodes;
  hint.classList.toggle('hidden', !inactive);
}

// The row is the whole story at a glance — an unexplained on/off toggle hides
// whether it will retry twice or ten times, over two seconds or two minutes.
function refreshRetrySummary() {
  var el = document.getElementById('prov-form-retry-summary');
  var enabled = document.getElementById('prov-form-retry-enabled');
  if (!el) return;
  if (!enabled || enabled.value !== 'true') {
    el.textContent = 'off';
    return;
  }
  var form = document.getElementById('provider-form');
  if (!form) return;
  var cfg = collectRetryConfig(form).config;
  el.textContent = cfg.max_retries + '× · ' + cfg.base_delay + 's → ' + cfg.max_delay + 's';
}

function setRetryForm(retry) {
  retry = retry || {};
  var enabled = retry.enabled != null ? retry.enabled : RETRY_DEFAULTS.enabled;
  var toggle = document.getElementById('prov-form-retry-toggle');
  var enabledInput = document.getElementById('prov-form-retry-enabled');
  if (toggle) toggle.classList.toggle('active', enabled);
  if (enabledInput) enabledInput.value = enabled ? 'true' : 'false';
  setInputValue('prov-form-retry-max', retry.max_retries != null ? retry.max_retries : RETRY_DEFAULTS.max_retries);
  setInputValue('prov-form-retry-base', retry.base_delay != null ? retry.base_delay : RETRY_DEFAULTS.base_delay);
  setInputValue('prov-form-retry-max-delay', retry.max_delay != null ? retry.max_delay : RETRY_DEFAULTS.max_delay);
  setInputChecked('prov-form-retry-rate', retry.on_rate_limit != null ? retry.on_rate_limit : RETRY_DEFAULTS.on_rate_limit);
  setInputChecked('prov-form-retry-server', retry.on_server_error != null ? retry.on_server_error : RETRY_DEFAULTS.on_server_error);
  setInputChecked('prov-form-retry-timeout', retry.on_timeout != null ? retry.on_timeout : RETRY_DEFAULTS.on_timeout);
  var extra = Array.isArray(retry.extra_statuses) ? retry.extra_statuses.join(', ') : '';
  setInputValue('prov-form-retry-extra', extra);
  refreshRetryHint();
}

function resetProviderForm() {
  var form = document.getElementById('provider-form');
  if (form) form.reset();
  setSelectValue('prov-form-type', 'openai_compat');
  document.getElementById('prov-form-edit-id').value = '';
  document.getElementById('prov-form-params').value = '{}';
  document.getElementById('prov-form-config').value = '{}';
  document.getElementById('api-key-input-prov-form').value = '';
  var keysInput = document.getElementById('prov-form-api-keys');
  if (keysInput) keysInput.value = '[]';
  _renderProviderKeys('prov-form', []);
  var routeDisplay = document.getElementById('or-route-display-prov-form');
  var quantDisplay = document.getElementById('or-quant-display-prov-form');
  if (routeDisplay) { routeDisplay.textContent = 'Auto (Any)'; routeDisplay.classList.add('text-muted'); }
  if (quantDisplay) { quantDisplay.textContent = 'Any'; quantDisplay.classList.add('text-muted'); }
  var tierInput = document.getElementById('prov-form-or-service-tier');
  var tierDisplay = document.getElementById('or-service-tier-display-prov-form');
  if (tierInput) tierInput.value = '';
  if (tierDisplay) { tierDisplay.textContent = 'Default (standard)'; tierDisplay.classList.add('text-muted'); }
  var nfToggle = document.getElementById('prov-form-or-no-fallbacks-toggle');
  var nfInput = document.getElementById('prov-form-or-no-fallbacks');
  if (nfToggle) nfToggle.classList.add('active');
  if (nfInput) nfInput.value = 'true';
  var ngRouteDisplay = document.getElementById('ng-route-display-prov-form');
  if (ngRouteDisplay) { ngRouteDisplay.textContent = 'Auto (Any)'; ngRouteDisplay.classList.add('text-muted'); }
  setInputValue('prov-form-ng-route', '');
  setRetryForm({});
  toggleProviderFields('prov-form');
}

function populateProviderForm(data) {
  document.getElementById('prov-form-name').value = data.name || '';
  setSelectValue('prov-form-type', data.type || 'openai_compat');
  document.getElementById('prov-form-base-url').value = data.base_url || '';
  toggleProviderFields('prov-form');
  var params = {};
  try { params = JSON.parse(data.params_json || '{}'); } catch (e) {}
  document.getElementById('prov-form-params').value = JSON.stringify(params);
  var config = {};
  try { config = JSON.parse(data.config_json || '{}'); } catch (e) {}
  document.getElementById('prov-form-config').value = JSON.stringify(config);
  var refs = Array.isArray(config.api_keys)
    ? config.api_keys.filter(function (r) { return typeof r === 'string' && r; })
    : [];
  if (!refs.length && data.api_key && data.api_key !== '__HIDDEN__') refs = [data.api_key];
  _setProviderKeys('prov-form', refs, { quiet: true });
  document.getElementById('model-text-prov-form').value = data.model || '';
  if (data.type === 'openrouter') {
    var savedRoute = config.or_route || '';
    var savedQuant = config.or_quant || '';
    var savedNoFallbacks = config.or_no_fallbacks !== false;
    document.getElementById('or-route-display-prov-form').textContent = savedRoute || 'Auto (Any)';
    document.getElementById('or-route-display-prov-form').classList.toggle('text-muted', !savedRoute);
    document.getElementById('prov-form-or-route').value = savedRoute;
    document.getElementById('or-quant-display-prov-form').textContent = savedQuant || 'Any';
    document.getElementById('or-quant-display-prov-form').classList.toggle('text-muted', !savedQuant);
    document.getElementById('prov-form-or-quant').value = savedQuant;
    var savedTier = config.or_service_tier || '';
    document.getElementById('prov-form-or-service-tier').value = savedTier;
    var tierDisplay = document.getElementById('or-service-tier-display-prov-form');
    tierDisplay.textContent = _orServiceTierLabel(savedTier);
    tierDisplay.classList.toggle('text-muted', !savedTier);
    if (data.model) {
      var nfToggle = document.getElementById('prov-form-or-no-fallbacks-toggle');
      var nfInput = document.getElementById('prov-form-or-no-fallbacks');
      if (nfToggle && nfInput) {
        nfToggle.classList.toggle('active', savedNoFallbacks);
        nfInput.value = savedNoFallbacks ? 'true' : 'false';
      }
      refreshNoFallbacksVisibility('prov-form');
      fetchOROptions(data.model);
    }
  }
  if (data.type === 'nanogpt') {
    var savedNgRoute = config.ng_route || '';
    var ngRouteDisplay = document.getElementById('ng-route-display-prov-form');
    document.getElementById('prov-form-ng-route').value = savedNgRoute;
    if (ngRouteDisplay) {
      ngRouteDisplay.textContent = savedNgRoute || 'Auto (Any)';
      ngRouteDisplay.classList.toggle('text-muted', !savedNgRoute);
    }
    fetchNGRouteOptions(data.model);
  }
  if (data.type === 'google_vertex') {
    document.getElementById('prov-form-vertex-project-id').value = config.vertex_project_id || '';
    setSelectValue('prov-form-vertex-region', config.vertex_region || 'global');
  }
  setRetryForm(config.retry || {});
}

window.sortProviders = function (mode) {
  _saveListPref('focus_providers_sort', mode);
  var grid = document.getElementById('providers-grid');
  if (!grid) return;
  var cards = Array.from(grid.querySelectorAll('[data-ui="entity-row"]'));
  cards.sort(function (a, b) {
    var aName = a.dataset.provName || '';
    var bName = b.dataset.provName || '';
    var aCreated = a.dataset.provCreated || '';
    var bCreated = b.dataset.provCreated || '';
    if (mode === 'az') return aName.localeCompare(bName);
    if (mode === 'za') return bName.localeCompare(aName);
    if (mode === 'oldest') return aCreated.localeCompare(bCreated);
    return bCreated.localeCompare(aCreated);
  });
  cards.forEach(function (card) { grid.appendChild(card); });
};

async function fetchProviderBalances() {
  document.querySelectorAll('[id^="balance-"]').forEach(async el => {
    const providerId = el.id.replace('balance-', '');
    try {
      const res = await hxFetch(api.providerBalance(providerId));
      if (!res.ok) {
        el.textContent = 'error';
        return;
      }
      const data = await res.json();
      const balances = data.balances || [];
      if (balances.length === 0) {
        el.textContent = 'unavailable';
        return;
      }
      el.textContent = balances.map(b => '$' + Number(b.amount).toFixed(2) + ' ' + b.currency).join(', ');
    } catch (e) {
      el.textContent = 'unavailable';
    }
  });
}

// The modal body is swapped in by htmx on open (see modal.js), so this must run
// per swap — not once at script load, when no provider cards exist yet.
function initProvidersModal() {
  const activeId = StateManager.get('provider_id');
  if (activeId && window.syncProviderHighlight) window.syncProviderHighlight(activeId);
  fetchProviderBalances();
  var sv = localStorage.getItem('focus_providers_sort');
  if (sv && window.sortProviders) window.sortProviders(sv);
}

document.body.addEventListener('htmx:afterSwap', function (evt) {
  if (evt.detail.target && evt.detail.target.id === 'providers-modal-body-inner') {
    initProvidersModal();
  }
});

window._currentSecretPrefix = null;

// The key library is its own surface: a banded list rendered from
// /partials/secrets, so the count and the rows come from one server render.
// `pick` is set when a provider's key list opened it; the add form is the
// separate modal-secret-new, so the list never changes height under the pointer.
function openSecretsModal(prefix) {
  window._currentSecretPrefix = prefix || null;
  var title = document.querySelector('#modal-secrets [data-ui="modal-title"]');
  if (title) title.textContent = prefix ? 'Select API Key' : 'Manage API Keys';
  openModal('modal-secrets');
  return Refresh.load('secretsList');
}

function openSecretsManager() {
  return openSecretsModal(null);
}

window.loadSecrets = function () {
  var pick = window._currentSecretPrefix ? '1' : '0';
  return hxGet(api.partials.secrets + '?pick=' + pick, {
    target: '#secrets-container',
    swap: 'innerHTML',
  });
};

function _secretRef(name) {
  return 'SECRET:' + name;
}

// Pick mode can inline a one-off key (no name) or save the named key and
// reference it; manage mode only saves. The opener owns the mode, so it also
// owns the copy that explains it.
window.actionOpenNewSecret = function () {
  var form = document.getElementById('secret-form');
  if (form) form.reset();
  var pick = !!window._currentSecretPrefix;
  var nameInput = document.getElementById('secret-name');
  var note = document.getElementById('secret-name-note');
  if (nameInput) nameInput.placeholder = pick ? 'Optional' : 'e.g. openrouter-main';
  if (note) {
    note.textContent = pick
      ? 'Leave the name blank to use the key once without saving it.'
      : 'Saved keys can be reused by any provider.';
  }
  openModal('modal-secret-new');
  if (nameInput) nameInput.focus();
};

window.actionUseSecret = function (el) {
  var prefix = window._currentSecretPrefix;
  if (!prefix) return;
  addProviderKey(prefix, _secretRef(el.dataset.name));
  closeModal('modal-secrets');
};

window.actionDeleteSecret = function (el) {
  var name = el.dataset.name;
  window.openConfirmModal('Delete the saved key <strong>' + window.escapeHtml(name) + '</strong>?', function () {
    Refresh.mutate(api.providerSecret(name), { method: 'DELETE' }, { changed: ['secrets'] }).then(function (res) {
      if (!res.ok) window.showErrorToast('Could not delete the key.');
    });
  });
};

window.actionSubmitSecretForm = function (form, e) {
  e.preventDefault();
  var nameInput = document.getElementById('secret-name');
  var valueInput = document.getElementById('secret-value');
  if (!nameInput || !valueInput) return;
  var name = nameInput.value.trim();
  var value = valueInput.value.trim();
  var prefix = window._currentSecretPrefix;
  if (!value) {
    valueInput.focus();
    window.showInfoToast('Paste a key or upload a service account JSON.');
    return;
  }
  if (!name) {
    if (prefix) {
      addProviderKey(prefix, value);
      closeModal('modal-secret-new', { discard: true });
      closeModal('modal-secrets');
      return;
    }
    nameInput.focus();
    window.showInfoToast('Give the key a name so you can find it again.');
    return;
  }
  hxJson(api.providerSecrets, 'POST', { name: name, value: value }).then(function (res) {
    if (!res.ok) {
      window.showErrorToast('Could not save the key.');
      return;
    }
    closeModal('modal-secret-new', { discard: true });
    if (prefix) {
      addProviderKey(prefix, _secretRef(name));
      closeModal('modal-secrets');
      return;
    }
    return Refresh.changed('secrets');
  });
};

window.actionLoadSecretFile = function (el) {
  var file = el.files && el.files[0];
  if (!file) return;
  var targetId = el.dataset.target;
  var nameInput = document.getElementById('secret-name');
  var reader = new FileReader();
  reader.onload = function (ev) {
    var target = document.getElementById(targetId);
    if (target) target.value = ev.target.result;
    if (nameInput && !nameInput.value) nameInput.value = file.name.replace(/\.json$/i, '');
  };
  reader.readAsText(file);
  el.value = '';
};

function _keyRowLabel(ref) {
  return ref.indexOf('SECRET:') === 0 ? 'Saved Key: ' + ref.slice(7) : 'Raw Key (hidden)';
}

function _getProviderKeys(prefix) {
  const input = document.getElementById(prefix + '-api-keys');
  let refs = [];
  try {
    refs = JSON.parse((input && input.value) || '[]');
  } catch (e) {}
  if (!Array.isArray(refs)) return [];
  return refs.filter(function (r) { return typeof r === 'string' && r; });
}

function _renderProviderKeys(prefix, refs) {
  const count = document.getElementById(prefix + '-key-count');
  if (count) count.textContent = refs.length === 1 ? '1 key' : refs.length + ' keys';
  const container = document.getElementById(prefix + '-key-list');
  if (!container) return;
  container.innerHTML = '';
  if (!refs.length) {
    const empty = document.createElement('div');
    empty.className = 'provider-keys-empty';
    const note = document.createElement('span');
    note.className = 'row-meta';
    note.textContent = 'No keys — add one if the endpoint requires authentication.';
    empty.appendChild(note);
    container.appendChild(empty);
    return;
  }
  const tpl = document.getElementById(prefix + '-key-row-template');
  refs.forEach(function (ref) {
    if (!tpl) return;
    const node = tpl.content.firstElementChild.cloneNode(true);
    node.dataset.ref = ref;
    node.dataset.prefix = prefix;
    const label = node.querySelector('[data-ui="key-row-label"]');
    if (label) {
      label.textContent = _keyRowLabel(ref);
      label.title = _keyRowLabel(ref);
    }
    container.appendChild(node);
  });
}

function _initProviderKeySortable(prefix) {
  const container = document.getElementById(prefix + '-key-list');
  if (!container || typeof Sortable === 'undefined') return;
  if (container._sortable) container._sortable.destroy();
  container._sortable = new Sortable(container, {
    animation: 150,
    ghostClass: 'sortable-ghost',
    handle: '.arranger-handle',
    onEnd: function () {
      const refs = Array.from(container.children)
        .map(function (c) { return c.dataset.ref; })
        .filter(Boolean);
      _setProviderKeys(prefix, refs, { skipRender: true, markDirty: true });
    },
  });
}

function _setProviderKeys(prefix, refs, opts) {
  opts = opts || {};
  const input = document.getElementById(prefix + '-api-keys');
  if (input) input.value = JSON.stringify(refs);
  const legacy = document.getElementById('api-key-input-' + prefix);
  if (legacy) legacy.value = refs[0] || '';
  if (!opts.skipRender) {
    _renderProviderKeys(prefix, refs);
    _initProviderKeySortable(prefix);
  }
  if (!opts.quiet && opts.markDirty && window.ModalController) {
    window.ModalController.setDirty('modal-provider-create', true);
  }
}

function addProviderKey(prefix, ref) {
  const refs = _getProviderKeys(prefix);
  if (refs.indexOf(ref) === -1) refs.push(ref);
  _setProviderKeys(prefix, refs, { markDirty: true });
}

window.actionRemoveProviderKey = function (el) {
  const row = el.closest('[data-ui="key-row"]');
  if (!row) return;
  const prefix = row.dataset.prefix || 'prov-form';
  const refs = _getProviderKeys(prefix).filter(function (r) { return r !== row.dataset.ref; });
  _setProviderKeys(prefix, refs, { markDirty: true });
};

