var PROVIDER_FIELD_CONFIG = {
  openrouter: {
    orFields: true,
    modelInput: true,
    baseUrl: false,
    vertexFields: false,
    modelRequired: true,
  },
  google_vertex: {
    orFields: false,
    modelInput: true,
    baseUrl: false,
    vertexFields: true,
    modelRequired: true,
  },
  google_aistudio: {
    orFields: false,
    modelInput: true,
    baseUrl: false,
    vertexFields: false,
    modelRequired: true,
  },
  deepseek: {
    orFields: false,
    modelInput: true,
    baseUrl: false,
    vertexFields: false,
    modelRequired: true,
  },
  moonshot: {
    orFields: false,
    modelInput: true,
    baseUrl: false,
    vertexFields: false,
    modelRequired: true,
  },
};

function toggleProviderFields(prefix) {
  var type = document.getElementById(prefix + '-type').value;
  var orFields = document.getElementById(prefix + '-or-fields');
  var modelInput = document.getElementById(prefix + '-model-input');
  var baseUrl = document.getElementById(prefix + '-baseurl');
  var vertexFields = document.getElementById(prefix + '-vertex-fields');

  var cfg = PROVIDER_FIELD_CONFIG[type] || {
    orFields: false,
    modelInput: true,
    baseUrl: true,
    vertexFields: false,
    modelRequired: true,
  };

  if (orFields) {
    orFields.classList.toggle('hidden', !cfg.orFields);
    orFields.classList.toggle('flex', cfg.orFields);
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
  document.getElementById('modal-fetch-models').classList.remove('hidden');
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

  let params = {};
  if (type === 'google_vertex') {
    const regionInput = document.getElementById(prefix + '-vertex-region');
    const projectInput = document.getElementById(prefix + '-vertex-project-id');
    if (regionInput) params.vertex_region = regionInput.value;
    if (projectInput) params.vertex_project_id = projectInput.value;
  }

  const editIdInput = document.getElementById('prov-form-edit-id');
  const providerId = editIdInput ? editIdInput.value : '';

  try {
    let body = { type, base_url: baseUrl, api_key: apiKey, params };
    if (providerId) body.provider_id = providerId;

    const res = await fetch(api.providerFetchModels, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

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
  if (type === 'openrouter') {
    fetchOROptions(id);
  }

  document.getElementById('modal-fetch-models').classList.add('hidden');
}

var _orRouteOptions = [{ value: '', label: 'Auto (Any)' }];
var _orQuantOptions = [{ value: '', label: 'Any' }];

function fetchOROptions(modelId) {
  if (!modelId) { _orRouteOptions = [{ value: '', label: 'Auto (Any)' }]; _orQuantOptions = [{ value: '', label: 'Any' }]; return; }
  fetch('/api/providers/openrouter/endpoints/' + encodeURIComponent(modelId))
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

var _optionModalCallback = null;

function openRouteSelectModal(prefix) {
  try {
    var data = Alpine.$data(document.getElementById('modal-select-option'));
    data.options = _orRouteOptions;
    data.title = 'Select Provider Routing';
    data.search = '';
  } catch (e) {}
  _optionModalCallback = function (value, label) {
    document.getElementById(prefix + '-or-route').value = value;
    document.getElementById('or-route-display-' + prefix).textContent = label;
    document.getElementById('or-route-display-' + prefix).classList.toggle('text-muted', !value);
    document.getElementById(prefix + '-or-route').dispatchEvent(new Event('change', { bubbles: true }));
  };
  openModal('modal-select-option');
}

function openQuantSelectModal(prefix) {
  try {
    var data = Alpine.$data(document.getElementById('modal-select-option'));
    data.options = _orQuantOptions;
    data.title = 'Select Quantization';
    data.search = '';
  } catch (e) {}
  _optionModalCallback = function (value, label) {
    document.getElementById(prefix + '-or-quant').value = value;
    document.getElementById('or-quant-display-' + prefix).textContent = label;
    document.getElementById('or-quant-display-' + prefix).classList.toggle('text-muted', !value);
  };
  openModal('modal-select-option');
}

function toggleNoFallbacks(prefix) {
  const toggle = document.getElementById(prefix + '-or-no-fallbacks-toggle');
  const input = document.getElementById(prefix + '-or-no-fallbacks');
  if (!toggle || !input) return;
  toggle.classList.toggle('active');
  input.value = toggle.classList.contains('active') ? 'true' : 'false';
}

function refreshNoFallbacksVisibility(prefix) {
  const routeInput = document.getElementById(prefix + '-or-route');
  const row = document.getElementById(prefix + '-or-no-fallbacks-row');
  if (!routeInput || !row) return;
  row.classList.toggle('hidden', !routeInput.value);
}

function setActiveProvider(id, name, type) {
  document.querySelectorAll('.provider-card').forEach((el) => el.classList.remove('active'));
  const card = document.getElementById('prov-card-' + id);
  if (card) card.classList.add('active');

  const sendBtn = document.getElementById('send-btn');
  if (sendBtn) sendBtn.dataset.providerId = id;
  StateManager.setProvider(id, type);
}

function extractData(form) {
  const data = Object.fromEntries(new FormData(form));
  if (data.api_key === '__HIDDEN__' || data.api_key === '') delete data.api_key;

  const type = data.type || form.querySelector('input[name="type"]').value;

  if (type === 'openrouter') {
    if (!data.model) {
      alert('Please select an OpenRouter model.');
      throw new Error('Model required');
    }
    data.base_url = 'https://openrouter.ai/api/v1';

    let params = {};
    try {
      params = JSON.parse(data.params || '{}');
    } catch (e) {}

    if (data.or_route) params.or_route = data.or_route;
    else delete params.or_route;

    if (data.or_quant) params.or_quant = data.or_quant;
    else delete params.or_quant;

    const orNoFallbacksInput = form.querySelector('[name="or_no_fallbacks"]');
    params.or_no_fallbacks = orNoFallbacksInput ? orNoFallbacksInput.value === 'true' : true;

    data.params = params;
  } else if (type === 'google_vertex') {
    let params = {};
    try {
      params = JSON.parse(data.params || '{}');
    } catch (e) {}
    if (data.vertex_region) params.vertex_region = data.vertex_region;
    if (data.vertex_project_id) params.vertex_project_id = data.vertex_project_id;
    data.params = params;
    data.base_url = '';
  } else if (type === 'google_aistudio' || type === 'deepseek' || type === 'moonshot') {
    try {
      data.params = JSON.parse(data.params || '{}');
    } catch (e) {
      data.params = {};
    }
    delete data.base_url;
  } else {
    try {
      data.params = JSON.parse(data.params || '{}');
    } catch (e) {
      data.params = {};
    }
  }

  delete data.or_route;
  delete data.or_quant;
  delete data.or_no_fallbacks;
  delete data.vertex_region;
  delete data.vertex_project_id;

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
  fetch(url, {
    method: method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  }).then(async function (r) {
    if (r.ok) {
      closeModal('modal-provider-create');
      htmx.ajax('GET', api.partials.providersModal, {
        target: '#providers-modal-body-inner',
        swap: 'innerHTML',
      });
    } else {
      var errBody;
      try { errBody = await r.json(); } catch (e) { errBody = await r.text(); }
      console.error('Provider save failed:', r.status, errBody);
    }
  });
}

window.openProviderEditModal = async function (id) {
  resetProviderForm();
  try {
    const res = await fetch(api.provider(id));
    if (!res.ok) return;
    const data = await res.json();
    populateProviderForm(data);
    document.getElementById('prov-form-edit-id').value = id;
    document.getElementById('prov-form-submit-btn').textContent = 'Save Provider';
    var titleEl = document.querySelector('#modal-provider-create .modal-title');
    if (titleEl) titleEl.textContent = 'Edit Provider';
    openModal('modal-provider-create');
  } catch (err) {
    console.error(err);
  }
};

window.openProviderCreateModal = function () {
  resetProviderForm();
  document.getElementById('prov-form-edit-id').value = '';
  document.getElementById('prov-form-submit-btn').textContent = 'Add Provider';
  var titleEl = document.querySelector('#modal-provider-create .modal-title');
  if (titleEl) titleEl.textContent = 'Add Provider';
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
    }));
  }
};

function resetProviderForm() {
  var form = document.getElementById('provider-form');
  if (form) form.reset();
  setSelectValue('prov-form-type', 'openai_compat');
  document.getElementById('prov-form-edit-id').value = '';
  document.getElementById('prov-form-params').value = '{}';
  document.getElementById('api-key-input-prov-form').value = '';
  document.getElementById('api-key-display-prov-form').innerHTML = '<span class="text-muted">Select API Key...</span>';
  var routeDisplay = document.getElementById('or-route-display-prov-form');
  var quantDisplay = document.getElementById('or-quant-display-prov-form');
  if (routeDisplay) { routeDisplay.textContent = 'Auto (Any)'; routeDisplay.classList.add('text-muted'); }
  if (quantDisplay) { quantDisplay.textContent = 'Any'; quantDisplay.classList.add('text-muted'); }
  var nfToggle = document.getElementById('prov-form-or-no-fallbacks-toggle');
  var nfInput = document.getElementById('prov-form-or-no-fallbacks');
  if (nfToggle) nfToggle.classList.add('active');
  if (nfInput) nfInput.value = 'true';
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
  var ak = data.api_key || '';
  if (ak.startsWith('SECRET:')) {
    document.getElementById('api-key-input-prov-form').value = ak;
    document.getElementById('api-key-display-prov-form').innerHTML = 'Saved Key: ' + ak.replace('SECRET:', '');
    document.getElementById('api-key-display-prov-form').classList.remove('text-muted');
  } else if (ak && ak !== '__HIDDEN__') {
    document.getElementById('api-key-input-prov-form').value = '';
    document.getElementById('api-key-display-prov-form').innerHTML = 'Raw Key (Hidden)';
    document.getElementById('api-key-display-prov-form').classList.remove('text-muted');
  }
  document.getElementById('model-text-prov-form').value = data.model || '';
  if (data.type === 'openrouter') {
    var savedRoute = params.or_route || '';
    var savedQuant = params.or_quant || '';
    var savedNoFallbacks = params.or_no_fallbacks !== false;
    document.getElementById('or-route-display-prov-form').textContent = savedRoute || 'Auto (Any)';
    document.getElementById('or-route-display-prov-form').classList.toggle('text-muted', !savedRoute);
    document.getElementById('or-quant-display-prov-form').textContent = savedQuant || 'Any';
    document.getElementById('or-quant-display-prov-form').classList.toggle('text-muted', !savedQuant);
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
  if (data.type === 'google_vertex') {
    document.getElementById('prov-form-vertex-project-id').value = params.vertex_project_id || '';
    setSelectValue('prov-form-vertex-region', params.vertex_region || 'global');
  }
}

window.sortProviders = function (mode) {
  _saveListPref('focus_providers_sort', mode);
  var grid = document.getElementById('providers-grid');
  if (!grid) return;
  var cards = Array.from(grid.querySelectorAll('.provider-card'));
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
      const res = await fetch(api.providerBalance(providerId));
      if (!res.ok) {
        el.textContent = 'Balance: error';
        return;
      }
      const data = await res.json();
      const balances = data.balances || [];
      if (balances.length === 0) {
        el.textContent = 'Balance: unavailable';
        return;
      }
      el.textContent = 'Balance: ' + balances.map(b => '$' + Number(b.amount).toFixed(2) + ' ' + b.currency).join(', ');
    } catch (e) {
      el.textContent = 'Balance: unavailable';
    }
  });
}

setTimeout(() => {
  document.addEventListener('option-selected', function (e) {
    if (_optionModalCallback) {
      _optionModalCallback(e.detail.value, e.detail.label);
      _optionModalCallback = null;
    }
  });
  const activeId = StateManager.get('provider_id');
  const activeType = StateManager.get('provider_type');
  if (activeId) setActiveProvider(activeId, '', activeType);
  fetchProviderBalances();
  var sv = localStorage.getItem('focus_providers_sort');
  if (sv && window.sortProviders) window.sortProviders(sv);
}, 100);

window._currentSecretPrefix = null;

function openSecretsModal(prefix) {
  window._currentSecretPrefix = prefix;
  var modal = document.getElementById('modal-secrets');
  modal.classList.remove('hidden');
  document.querySelectorAll('#modal-secrets .secret-select-btn').forEach(function (btn) {
    btn.classList.toggle('hidden', !prefix);
  });
  document.querySelector('#modal-secrets .secrets-title').textContent = prefix ? 'Select API Key' : 'Manage API Keys';
  fetchSecrets();
}

function openSecretsManager() {
  openSecretsModal(null);
}

async function fetchSecrets() {
  try {
    const res = await fetch(api.providerSecrets);
    const data = await res.json();
    window.dispatchEvent(new CustomEvent('secrets-loaded', { detail: data.data }));
  } catch (err) {
    console.error(err);
  }
}

async function saveNewSecret(name, value) {
  if (!name || !value) return;
  await fetch(api.providerSecrets, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, value }),
  });
  fetchSecrets();
}

async function deleteSecret(name) {
  if (!confirm('Delete this saved key?')) return;
  await fetch(api.providerSecret(name), { method: 'DELETE' });
  fetchSecrets();
}

function _setKeyInput(val, displayHtml) {
  const prefix = window._currentSecretPrefix;
  if (!prefix) return;
  const input = document.getElementById('api-key-input-' + prefix);
  const display = document.getElementById('api-key-display-' + prefix);
  if (input) input.value = val;
  if (display) {
    display.innerHTML = displayHtml;
    display.classList.remove('text-muted');
  }
  document.getElementById('modal-secrets').classList.add('hidden');
}

function selectSecret(name) {
  _setKeyInput('SECRET:' + name, 'Saved Key: ' + name);
}

function selectRawKey(val) {
  if (!val) return;
  _setKeyInput(val, 'Raw Key (Hidden)');
}

function clearKey() {
  const prefix = window._currentSecretPrefix;
  if (!prefix) return;
  const input = document.getElementById('api-key-input-' + prefix);
  const display = document.getElementById('api-key-display-' + prefix);
  if (input) input.value = '';
  if (display) {
    display.innerHTML = '<span class="text-muted">Select API Key...</span>';
  }
  document.getElementById('modal-secrets').classList.add('hidden');
}
