var PROVIDER_FIELD_CONFIG = {
  openrouter: {
    orFields: true,
    modelInput: false,
    baseUrl: false,
    vertexFields: false,
    modelRequired: false,
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

function selectFetchedModel(id, name) {
  const prefix = window._currentFetchPrefix;
  if (!prefix) return;

  const type = document.getElementById(prefix + '-type')?.value;

  if (type === 'openrouter') {
    const input = document.getElementById('or-model-input-' + prefix);
    if (input) {
      input.value = id;
      const display = document.getElementById('or-model-display-' + prefix);
      display.textContent = name || id;
      display.classList.remove('text-muted');
    }
    _fetchOROptions(id, '', '');
  } else {
    const input = document.getElementById('model-text-' + prefix);
    if (input) input.value = id;
  }

  document.getElementById('modal-fetch-models').classList.add('hidden');
}

function _fetchOROptions(modelId, selectedRoute, selectedQuant) {
  var url = '/partials/providers/openrouter-options/' + encodeURIComponent(modelId);
  if (selectedRoute || selectedQuant) {
    url += '?route=' + encodeURIComponent(selectedRoute || '') + '&quant=' + encodeURIComponent(selectedQuant || '');
  }
  fetch(url)
    .then(function (r) { return r.text(); })
    .then(function (html) {
      var temp = document.createElement('div');
      temp.innerHTML = html;
      ['prov-form-route-wrapper', 'prov-form-or-no-fallbacks-row', 'prov-form-quant-wrapper'].forEach(function (id) {
        var newEl = temp.querySelector('#' + id);
        var oldEl = document.getElementById(id);
        if (newEl && oldEl) oldEl.replaceWith(newEl);
      });
    });
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
    data.model = data.or_model;
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

  delete data.or_model;
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

window.setSelectValue = function (inputId, value) {
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
  document.getElementById('or-model-input-prov-form').value = '';
  document.getElementById('or-model-display-prov-form').textContent = 'Select Model...';
  document.getElementById('or-model-display-prov-form').classList.add('text-muted');
  var nfToggle = document.getElementById('prov-form-or-no-fallbacks-toggle');
  var nfInput = document.getElementById('prov-form-or-no-fallbacks');
  if (nfToggle) nfToggle.classList.add('active');
  if (nfInput) nfInput.value = 'true';
  var init = document.getElementById('prov-form-or-options-init');
  if (init) {
    var clone = init.content.cloneNode(true);
    ['prov-form-route-wrapper', 'prov-form-or-no-fallbacks-row', 'prov-form-quant-wrapper'].forEach(function (id) {
      var oldEl = document.getElementById(id);
      var newEl = clone.querySelector('#' + id);
      if (oldEl && newEl) oldEl.replaceWith(newEl);
    });
  }
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
  if (data.type === 'openrouter') {
    document.getElementById('or-model-input-prov-form').value = data.model || '';
    var display = document.getElementById('or-model-display-prov-form');
    display.textContent = data.model || 'Select Model...';
    display.classList.toggle('text-muted', !data.model);
    var savedRoute = params.or_route || '';
    var savedQuant = params.or_quant || '';
    var savedNoFallbacks = params.or_no_fallbacks !== false;
    if (data.model) {
      var nfToggle = document.getElementById('prov-form-or-no-fallbacks-toggle');
      var nfInput = document.getElementById('prov-form-or-no-fallbacks');
      if (nfToggle && nfInput) {
        nfToggle.classList.toggle('active', savedNoFallbacks);
        nfInput.value = savedNoFallbacks ? 'true' : 'false';
      }
      refreshNoFallbacksVisibility('prov-form');
      _fetchOROptions(data.model, savedRoute, savedQuant);
    }
  } else {
    document.getElementById('model-text-prov-form').value = data.model || '';
  }
  if (data.type === 'google_vertex') {
    document.getElementById('prov-form-vertex-project-id').value = params.vertex_project_id || '';
    setSelectValue('prov-form-vertex-region', params.vertex_region || 'global');
  }
}

function _saveListPref(key, value) {
  localStorage.setItem(key, value);
  fetch('/api/settings', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ key: key, value: value }),
  });
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
