function _providerKeys(provider) {
  if (!provider) return { refs: [], active: 0 };
  let config = {};
  try {
    config = JSON.parse(provider.config_json || '{}');
  } catch (e) {}
  let refs = Array.isArray(config.api_keys)
    ? config.api_keys.filter(function (k) { return typeof k === 'string' && k; })
    : [];
  if (!refs.length && provider.api_key) refs = [provider.api_key];
  let active = refs.indexOf(config.active_key);
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
    let config = {};
    try { config = JSON.parse(provider.config_json || '{}'); } catch (e) {}
    config.active_key = ref;
    provider.config_json = JSON.stringify(config);
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

var _summaryRun = null; // active summarize run: { chatId, stopRequested, watchdog, cancel }

window.summaryRunActive = function () {
  return _summaryRun !== null;
};

// Stop contract (mirrors Generation.stop, scaled down): POST the stop so the
// server cancels the buffered provider call, wait for the terminal event,
// hard-abort the stream if none arrives.
window.stopSummary = function () {
  var run = _summaryRun;
  if (!run || run.stopRequested) return;
  run.stopRequested = true;
  window.showInfoToast('Stopping summary\u2026', { duration: 6000 });

  var postCtl = new AbortController();
  var postTimer = setTimeout(function () { postCtl.abort(); }, 4000);
  fetch(window.api.chatStopSummary(run.chatId), { method: 'POST', signal: postCtl.signal })
    .then(function (r) {
      // 404: the run already finished; resolve locally instead of draining.
      if (r.status === 404) run.cancel();
    })
    .catch(function () {})
    .finally(function () { clearTimeout(postTimer); });

  run.watchdog = setTimeout(function () { run.cancel(); }, 6000);
};

function summarizeChat(chatId, messageId, btn) {
  if (!chatId) return;
  if (_summaryRun) {
    window.showErrorToast('A summary is already running');
    return;
  }
  window.openConfirmModal(
    messageId
      ? 'Summarize the conversation up to this message? A new chat is forked with the summary and recent messages as context.'
      : 'Summarize the conversation? A new chat is forked with the summary and recent messages as context.',
    function () { startSummary(chatId, messageId, btn); },
  );
}

function startSummary(chatId, messageId, btn) {
  var finished = false;
  var abortCtl = new AbortController();
  var run = { chatId: chatId, stopRequested: false, watchdog: null, cancel: null };

  function teardown() {
    if (_summaryRun === run) _summaryRun = null;
    if (run.watchdog) clearTimeout(run.watchdog);
    window.setGeneratingUI(false);
    if (btn) btn.disabled = false;
  }

  function fail(message) {
    if (finished) return;
    finished = true;
    teardown();
    window.resetRetryFeedback();
    window.hideInfoToast();
    window.showErrorToast(message || 'Summarize failed');
  }

  function cancelled() {
    if (finished) return;
    finished = true;
    teardown();
    abortCtl.abort();
    window.resetRetryFeedback();
    window.hideInfoToast();
    window.showSuccessToast('Summary cancelled');
  }
  run.cancel = cancelled;

  function handleEvent(raw) {
    var line = raw.trim();
    if (line.indexOf('data:') !== 0) return;
    var data;
    try { data = JSON.parse(line.slice(5).trim()); } catch (e) { return; }

    if (data.type === 'retry') {
      window.startRetryFeedback(data);
    } else if (data.type === 'error') {
      fail(data.error);
    } else if (data.type === 'done') {
      if (finished) return;
      if (data.cancelled) { cancelled(); return; }
      finished = true;
      teardown();
      window.resetRetryFeedback();
      window.hideInfoToast();
      window.location.href = '/chat/' + data.id;
    }
  }

  _summaryRun = run;
  if (btn) btn.disabled = true;
  window.setGeneratingUI(true);
  window.showInfoToast('Summarizing\u2026', { id: 'summarize', duration: 0 });

  fetch(window.api.chatSummarize(chatId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      provider_id: StateManager.get('provider_id') || '',
      message_id: messageId || '',
    }),
    signal: abortCtl.signal,
  })
    .then(function (resp) {
      if (!resp.ok) {
        return resp.text().then(function (t) {
          var msg = t;
          try { msg = JSON.parse(t).detail || t; } catch (e) { /* keep raw */ }
          throw new Error(msg || 'Summarize failed');
        });
      }
      var reader = resp.body.getReader();
      var decoder = new TextDecoder();
      var buffer = '';
      (function pump() {
        reader.read().then(function (result) {
          if (result.done) {
            if (!finished) fail('Summary stream ended unexpectedly');
            return;
          }
          buffer += decoder.decode(result.value, { stream: true });
          var chunks = buffer.split('\n\n');
          buffer = chunks.pop();
          chunks.forEach(handleEvent);
          pump();
        }).catch(function (e) { fail(e.message); });
      })();
    })
    .catch(function (e) {
      if (run.stopRequested) cancelled();
      else fail(e.message);
    });
}
