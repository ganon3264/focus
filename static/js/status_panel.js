function updateStatusPanel() {
  const activeId = StateManager.get('provider_id');
  const providerEl = document.getElementById('status-provider');
  const presetEl = document.getElementById('status-preset');
  const modelEl = document.getElementById('status-model');

  if (!activeId) {
    providerEl.textContent = 'None';
    modelEl.textContent = 'None';
  } else {
    let provider = window.APP_PROVIDERS.find(p => p.id === activeId);

    if (!provider) {
      const cardDisplay = document.getElementById('prov-display-' + activeId);
      if (cardDisplay) {
        const nameEl = cardDisplay.querySelector('strong');
        const typeModelEl = cardDisplay.querySelector('.text-muted');
        if (nameEl && typeModelEl) {
          const text = typeModelEl.textContent;
          const parts = text.split('•').map(s => s.trim());
          provider = {
            name: nameEl.textContent,
            type: parts.length > 0 ? parts[0] : 'Unknown',
            model: parts.length > 1 ? parts[1] : 'Unknown'
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
}

window.addEventListener('provider-changed', updateStatusPanel);
updateStatusPanel();

document.body.addEventListener('htmx:afterSwap', function(evt){
  if(evt.detail.target.id === 'providers-modal-body'){
    setTimeout(updateStatusPanel, 50);
  }
});

document.addEventListener('DOMContentLoaded', function(){
  const presetSelect = document.querySelector('#preset-selector select');
  if(presetSelect && presetSelect.value){
    htmx.ajax('GET', api.partials.promptArranger(presetSelect.value), {target:'#prompt-arranger', swap:'innerHTML'});
  }
});

function newChat(){
  fetch(api.chats, {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(StateManager.getAll())
  }).then(r => {
    if(!r.ok) throw new Error('Failed to create chat');
    return r.json();
  }).then(data => {
    window.location.href = '/chat/' + data.id;
  }).catch(e => alert(e.message));
}
