function _providerKeys(provider) {
  if (!provider) return { refs: [], active: 0 };
  let params = {};
  try {
    params = JSON.parse(provider.params_json || '{}');
  } catch (e) {}
  let refs = Array.isArray(params.api_keys)
    ? params.api_keys.filter(function (k) { return typeof k === 'string' && k; })
    : [];
  if (!refs.length && provider.api_key) refs = [provider.api_key];
  let active = refs.indexOf(params.active_key);
  if (active < 0) active = 0;
  return { refs: refs, active: active };
}

function _keyLabel(ref) {
  if (typeof ref !== 'string') return 'Key';
  return ref.indexOf('SECRET:') === 0 ? ref.slice(7) : 'Raw key';
}

function updateKeySwitcher(provider) {
  const row = document.getElementById('status-key-row');
  if (!row) return;
  const keys = _providerKeys(provider);
  const multi = keys.refs.length > 1;
  row.classList.toggle('hidden', !multi);
  row.classList.toggle('flex', multi);
  if (!multi) return;
  const countEl = document.getElementById('status-key-count');
  if (countEl) countEl.textContent = (keys.active + 1) + '/' + keys.refs.length;
}

window.actionShiftProviderKey = async function (el) {
  const activeId = StateManager.get('provider_id');
  const provider = activeId && (window.APP_PROVIDERS || []).find(function (p) { return p.id === activeId; });
  if (!provider) return;
  const dir = parseInt(el.dataset.dir, 10) || 0;
  const keys = _providerKeys(provider);
  const n = keys.refs.length;
  if (!dir || !n) return;
  const target = (keys.active + dir + n) % n;
  const ref = keys.refs[target];
  try {
    const res = await fetch(api.providerActiveKey(provider.id), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: ref }),
    });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    let params = {};
    try { params = JSON.parse(provider.params_json || '{}'); } catch (e) {}
    params.active_key = ref;
    provider.params_json = JSON.stringify(params);
    updateKeySwitcher(provider);
    if (window.showInfoToast) window.showInfoToast('Key ' + (target + 1) + '/' + keys.refs.length + ' · ' + _keyLabel(ref));
  } catch (err) {
    if (window.showErrorToast) window.showErrorToast('Could not switch key: ' + err.message);
    updateKeySwitcher(provider);
  }
};

function updateStatusPanel() {
  const activeId = StateManager.get('provider_id');
  const providerEl = document.getElementById('status-provider');
  const presetEl = document.getElementById('status-preset');
  const modelEl = document.getElementById('status-model');
  let provider = null;

  if (!activeId) {
    providerEl.textContent = 'None';
    modelEl.textContent = 'None';
  } else {
    provider = (window.APP_PROVIDERS || []).find((p) => p.id === activeId);

    if (!provider) {
      const cardDisplay = document.getElementById('prov-display-' + activeId);
      if (cardDisplay) {
        const nameEl = cardDisplay.querySelector('strong');
        const typeModelEl = cardDisplay.querySelector('.text-muted');
        if (nameEl && typeModelEl) {
          const text = typeModelEl.textContent;
          const parts = text.split('•').map((s) => s.trim());
          provider = {
            name: nameEl.textContent,
            type: parts.length > 0 ? parts[0] : 'Unknown',
            model: parts.length > 1 ? parts[1] : 'Unknown',
          };
        }
      }
    }

    if (provider) {
      providerEl.textContent = provider.type;
      presetEl.textContent = provider.name;
      modelEl.textContent = provider.model || 'Unknown';
      providerEl.title = provider.type;
      presetEl.title = provider.name;
      modelEl.title = provider.model || 'Unknown';
    } else {
      providerEl.textContent = 'Unknown';
      presetEl.textContent = 'Unknown';
      modelEl.textContent = 'Unknown';
      providerEl.title = 'Unknown';
      presetEl.title = 'Unknown';
      modelEl.title = 'Unknown';
    }
  }
  updateKeySwitcher(provider);
}

function updateCacheTimer() {
  const activeId = StateManager.get('provider_id');
  const cacheRow = document.getElementById('status-cache-row');
  const cacheEl = document.getElementById('status-cache');
  if (!cacheRow || !cacheEl) return;

  const provider =
    activeId && window.APP_PROVIDERS && window.APP_PROVIDERS.find((p) => p.id === activeId);

  if (!window.isClaudeProvider || !window.isClaudeProvider(provider)) {
    cacheRow.classList.add('hidden');
    return;
  }

  cacheRow.classList.remove('hidden');

  const remaining = window.getClaudeCacheTimer ? window.getClaudeCacheTimer(activeId) : null;

  if (!remaining) {
    cacheEl.textContent = '—';
    cacheEl.style.color = 'var(--text-muted)';
    return;
  }

  cacheEl.style.color = '';
  const totalSec = Math.floor(remaining / 1000);
  const min = Math.floor(totalSec / 60);
  const sec = totalSec % 60;
  cacheEl.textContent = min + 'm ' + (sec < 10 ? '0' : '') + sec + 's';
}

window.addEventListener('provider-changed', function () {
  updateStatusPanel();
  updateCacheTimer();
});
updateStatusPanel();
updateCacheTimer();
setInterval(updateCacheTimer, 1000);

document.body.addEventListener('htmx:afterSwap', function (evt) {
  if (evt.detail.target.id === 'providers-modal-body') {
    setTimeout(updateStatusPanel, 50);
  }
});

function newChat() {
  fetch(window.api.chats, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(StateManager.getAll()),
  })
    .then((r) => {
      if (!r.ok) throw new Error('Failed to create chat');
      return r.json();
    })
    .then((data) => {
      window.location.href = '/chat/' + data.id;
    })
    .catch((e) => window.showErrorToast(e.message));
}
