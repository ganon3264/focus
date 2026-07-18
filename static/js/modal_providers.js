window._OR_MODELS_CACHE = window._OR_MODELS_CACHE || [];
window._currentORPrefix = null;

function toggleProviderFields(prefix) {
  const type = document.getElementById(prefix + '-type').value;
  const orFields = document.getElementById(prefix + '-or-fields');
  const modelInput = document.getElementById(prefix + '-model-input');
  const baseUrl = document.getElementById(prefix + '-baseurl');
  const vertexFields = document.getElementById(prefix + '-vertex-fields');
  
  if (type === 'openrouter') {
    if(orFields) { orFields.classList.remove('hidden'); orFields.classList.add('flex'); }
    if(modelInput) modelInput.classList.add('hidden');
    if(baseUrl) baseUrl.classList.add('hidden');
    if(modelInput) modelInput.querySelector('input').removeAttribute('required');
    if(vertexFields) { vertexFields.classList.add('hidden'); vertexFields.classList.remove('flex'); }
  } else if (type === 'google_vertex') {
    if(orFields) { orFields.classList.add('hidden'); orFields.classList.remove('flex'); }
    if(modelInput) modelInput.classList.remove('hidden');
    if(baseUrl) baseUrl.classList.add('hidden');
    if(modelInput) modelInput.querySelector('input').setAttribute('required', 'required');
    if(vertexFields) { vertexFields.classList.remove('hidden'); vertexFields.classList.add('flex'); }
  } else if (type === 'google_aistudio' || type === 'deepseek' || type === 'moonshot') {
    if(orFields) { orFields.classList.add('hidden'); orFields.classList.remove('flex'); }
    if(modelInput) modelInput.classList.remove('hidden');
    if(baseUrl) baseUrl.classList.add('hidden');
    if(modelInput) modelInput.querySelector('input').setAttribute('required', 'required');
    if(vertexFields) { vertexFields.classList.add('hidden'); vertexFields.classList.remove('flex'); }
  } else {
    if(orFields) { orFields.classList.add('hidden'); orFields.classList.remove('flex'); }
    if(modelInput) modelInput.classList.remove('hidden');
    if(baseUrl) baseUrl.classList.remove('hidden');
    if(modelInput) modelInput.querySelector('input').setAttribute('required', 'required');
    if(vertexFields) { vertexFields.classList.add('hidden'); vertexFields.classList.remove('flex'); }
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
  document.getElementById('modal-fetch-models').style.display = 'grid';
  forceFetchModels();
}

async function forceFetchModels() {
  const prefix = window._currentFetchPrefix;
  if (!prefix) return;
  
  window.dispatchEvent(new CustomEvent('models-loading'));
  
  // Extract data from the form to send to backend
  let type = document.getElementById(prefix + '-type')?.value;
  if (!type && prefix !== 'new-prov') {
     type = document.getElementById('edit-prov-type-' + prefix)?.value;
  }
  
  const baseUrlInput = document.querySelector(`#provider-edit-${prefix} input[name="base_url"]`) || document.querySelector(`#new-prov-baseurl input[name="base_url"]`);
  const baseUrl = baseUrlInput ? baseUrlInput.value : '';
  
  const apiKeyInput = document.getElementById('api-key-input-' + prefix);
  let apiKey = apiKeyInput ? apiKeyInput.value : '';
  
  // Vertex needs region
  let params = {};
  if (type === 'google_vertex') {
    const regionInput = document.getElementById('edit-prov-vertex-region-' + prefix) || document.getElementById('new-prov-vertex-region');
    const projectInput = document.getElementById('edit-prov-vertex-project-id-' + prefix) || document.getElementById('new-prov-vertex-project-id');
    if (regionInput) {
       params.vertex_region = regionInput.value;
    }
    if (projectInput) {
       params.vertex_project_id = projectInput.value;
    }
  }

  try {
    const res = await fetch(api.providerFetchModels, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, base_url: baseUrl, api_key: apiKey, params })
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
  
  const type = document.getElementById(prefix + '-type')?.value || document.getElementById('edit-prov-type-' + prefix)?.value;
  
  if (type === 'openrouter') {
    const input = document.getElementById('or-model-input-' + prefix);
    if (input) {
      input.value = id;
      const display = document.getElementById('or-model-display-' + prefix);
      display.textContent = name || id;
      display.classList.remove('text-muted');
    }
    updateOpenRouterOptions(prefix, id);
  } else {
    const input = document.getElementById('model-text-' + prefix);
    if (input) {
      input.value = id;
    }
  }
  
  document.getElementById('modal-fetch-models').style.display = 'none';
}

function openORModelModal(prefix) {
  openFetchModelModal(prefix);
}
function renderMacroSelect(name, id, options, selectedValue) {
  // Finds the selected label
  let selectedLabel = "— Select —";
  for(let o of options) {
    if(o.value === selectedValue) selectedLabel = o.label;
  }
  const escapedLabel = selectedLabel.replace(/'/g, "\\'");
  
  // Creates an options html string for Alpine template
  let optionsHtml = '';
  options.forEach((opt, idx) => {
    const isFirst = idx === 0;
    const escOptLabel = opt.label.replace(/'/g, "\\'");
    optionsHtml += `
     <div class="px-3 py-2 cursor-pointer transition-colors duration-150 form-control text-sm w-full"
          ${isFirst ? '' : 'style="border-top: 1px solid var(--border);"'}
          onmouseover="this.style.background='var(--surface-3)'"
          onmouseout="this.style.background='transparent'"
          @click="
            selectedValue = '${opt.value}';
            selectedLabel = '${escOptLabel}';
            open = false;
            $nextTick(() => {
                const el = document.getElementById('${id}');
                el.value = selectedValue;
                el.dispatchEvent(new Event('change', { bubbles: true }));
            });
          "
     >
       ${opt.label}
     </div>
    `;
  });

  return `
    <div class="relative w-full" x-data="{ open: false, selectedValue: '${selectedValue}', selectedLabel: '${escapedLabel}' }">
      <input type="hidden" name="${name}" id="${id}" :value="selectedValue">
      <button type="button" @click="open = !open" class="flex justify-between items-center text-left w-full form-control text-sm w-full" style="cursor: pointer;">
         <span x-text="selectedLabel" class="truncate font-medium"></span>
         <span class="text-xs text-muted" style="transition: transform 0.2s;" :style="open ? 'transform: rotate(180deg);' : ''">▼</span>
      </button>
      <div x-show="open" @click.away="open = false" x-transition.opacity.duration.200ms
           class="absolute top-full left-0 right-0 mt-1 z-50 max-h-60 overflow-y-auto"
           style="background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-md); box-shadow: var(--shadow-lg); display: none;">
         ${optionsHtml}
      </div>
    </div>
  `;
}

async function updateOpenRouterOptions(prefix, modelId) {
  if (!modelId) return;

  try {
    const res = await fetch(api.providerOREndpoint(modelId));
    if (!res.ok) throw new Error('Failed to fetch endpoints');
    const data = await res.json();
    
    const endpoints = data.data?.endpoints || [];
    
    // Route options
    const routeOptions = [{value: "", label: "Auto (Any)"}];
    const providers = new Set();
    endpoints.forEach(ep => {
      if(ep.provider_name) providers.add(ep.provider_name);
    });
    providers.forEach(p => {
      routeOptions.push({value: p, label: p});
    });
    
    // Quantization options
    const quantOptions = [{value: "", label: "Any"}];
    const quants = new Set();
    endpoints.forEach(ep => {
      if(ep.quantization && ep.quantization !== 'unknown') quants.add(ep.quantization);
    });
    quants.forEach(q => {
      quantOptions.push({value: q, label: q});
    });

    // Replace the inner HTML of the wrapper divs with a freshly rendered Alpine component
    const routeWrapperId = prefix === 'new-prov' ? 'new-prov-route-wrapper' : 'edit-prov-route-wrapper-' + prefix;
    const routeInputId = prefix === 'new-prov' ? 'new-prov-or-route' : 'edit-prov-or-route-' + prefix;
    const rWrap = document.getElementById(routeWrapperId);
    if(rWrap) rWrap.innerHTML = renderMacroSelect('or_route', routeInputId, routeOptions, '');
    
    const quantWrapperId = prefix === 'new-prov' ? 'new-prov-quant-wrapper' : 'edit-prov-quant-wrapper-' + prefix;
    const quantInputId = prefix === 'new-prov' ? 'new-prov-or-quant' : 'edit-prov-or-quant-' + prefix;
    const qWrap = document.getElementById(quantWrapperId);
    if(qWrap) qWrap.innerHTML = renderMacroSelect('or_quant', quantInputId, quantOptions, '');

  } catch(err) {
     console.error(err);
  }
}

function setActiveProvider(id, name, type) {
  document.querySelectorAll('.provider-card').forEach(el => {
    el.style.borderColor = 'var(--border)';
    el.style.boxShadow = 'none';
  });
  const card = document.getElementById('prov-card-' + id);
  if(card) {
    card.style.borderColor = 'var(--accent)';
    card.style.boxShadow = 'var(--shadow-glow)';
  }
  
  const sendBtn = document.getElementById('send-btn');
  if(sendBtn) sendBtn.dataset.providerId = id;
  localStorage.setItem('pyvern-provider-id', id);
  if (type) {
    localStorage.setItem('pyvern-provider-type', type);
    window.dispatchEvent(new CustomEvent('provider-changed', { detail: type }));
  }
}

function toggleProviderEdit(id){
  const card = document.getElementById('prov-card-' + id);
  const form = document.getElementById('provider-edit-' + id);
  const display = document.getElementById('prov-display-' + id);
  if(form.classList.contains('hidden')){
    card.classList.add('col-span-full');
    form.classList.remove('hidden');
    form.style.display = 'flex';
    display.classList.add('hidden');
  } else {
    card.classList.remove('col-span-full');
    form.classList.add('hidden');
    form.style.display = 'none';
    display.classList.remove('hidden');
  }
}

function extractData(form) {
  const data = Object.fromEntries(new FormData(form));
  if(data.api_key === '__HIDDEN__' || data.api_key === '') delete data.api_key;
  
  const type = data.type || form.querySelector('input[name="type"]').value;
  
  if (type === 'openrouter') {
    data.model = data.or_model;
    if (!data.model) {
      alert('Please select an OpenRouter model.');
      throw new Error('Model required');
    }
    data.base_url = 'https://openrouter.ai/api/v1';
    
    let params = {};
    try { params = JSON.parse(data.params || '{}'); } catch(e){}
    
    if (data.or_route) params.or_route = data.or_route;
    else delete params.or_route;
    
    if (data.or_quant) params.or_quant = data.or_quant;
    else delete params.or_quant;
    
    data.params = params;
  } else if (type === 'google_vertex') {
    let params = {};
    try { params = JSON.parse(data.params || '{}'); } catch(e){}
    if (data.vertex_region) params.vertex_region = data.vertex_region;
    if (data.vertex_project_id) params.vertex_project_id = data.vertex_project_id;
    data.params = params;
    data.base_url = '';
  } else if (type === 'google_aistudio' || type === 'deepseek' || type === 'moonshot') {
    try { data.params = JSON.parse(data.params || '{}'); } catch(e){ data.params = {}; }
    data.base_url = '';
  } else {
    try { data.params = JSON.parse(data.params || '{}'); } catch(e){ data.params = {}; }
  }
  
  delete data.or_model;
  delete data.or_route;
  delete data.or_quant;
  delete data.vertex_region;
  delete data.vertex_project_id;
  
  return data;
}

function saveProviderModal(e, id){
  e.preventDefault();
  let data;
  try { data = extractData(e.target); } catch(err) { return; }
  fetch(api.provider(id), {
    method: 'PATCH',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  }).then(function(r){
    if(r.ok) htmx.ajax('GET', api.partials.providersModal, {target:'#providers-modal-body',swap:'innerHTML'});
  });
}

function submitProviderModal(e){
  e.preventDefault();
  let data;
  try { data = extractData(e.target); } catch(err) { return; }
  fetch(api.providers, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  }).then(function(r){
    if(r.ok) htmx.ajax('GET', api.partials.providersModal, {target:'#providers-modal-body',swap:'innerHTML'});
  });
}

// Initialization
setTimeout(() => {
  const activeId = localStorage.getItem('pyvern-provider-id');
  const activeType = localStorage.getItem('pyvern-provider-type');
  if (activeId) setActiveProvider(activeId, '', activeType);
}, 100);


window._currentSecretPrefix = null;

function openSecretsModal(prefix) {
  window._currentSecretPrefix = prefix;
  document.getElementById('modal-secrets').style.display = 'grid';
  fetchSecrets();
}

async function fetchSecrets() {
  try {
    const res = await fetch(api.providerSecrets);
    const data = await res.json();
    window.dispatchEvent(new CustomEvent('secrets-loaded', { detail: data.data }));
  } catch (err) { console.error(err); }
}

async function saveNewSecret(name, value) {
  if(!name || !value) return;
  await fetch(api.providerSecrets, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({name, value})
  });
  fetchSecrets();
}

async function deleteSecret(name) {
  if(!confirm('Delete this saved key?')) return;
  await fetch(api.providerSecret(name), { method: 'DELETE' });
  fetchSecrets();
}

function _setKeyInput(val, displayHtml) {
  const prefix = window._currentSecretPrefix;
  if (!prefix) return;
  const input = document.getElementById('api-key-input-' + prefix);
  const display = document.getElementById('api-key-display-' + prefix);
  if(input) input.value = val;
  if(display) {
    display.innerHTML = displayHtml;
    display.classList.remove('text-muted');
  }
  document.getElementById('modal-secrets').style.display = 'none';
}

function selectSecret(name) {
  _setKeyInput('SECRET:' + name, 'Saved Key: ' + name);
}

function selectRawKey(val) {
  if(!val) return;
  _setKeyInput(val, 'Raw Key (Hidden)');
}

function clearKey() {
  const prefix = window._currentSecretPrefix;
  if (!prefix) return;
  const input = document.getElementById('api-key-input-' + prefix);
  const display = document.getElementById('api-key-display-' + prefix);
  if(input) input.value = '';
  if(display) {
    display.innerHTML = '<span class="text-muted">Select API Key...</span>';
  }
  document.getElementById('modal-secrets').style.display = 'none';
}
