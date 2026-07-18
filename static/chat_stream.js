(function(){
  let currentController = null;
  const sendBtn = document.getElementById('send-btn');
  const stopBtn = document.getElementById('stop-btn');
  const input = document.getElementById('chat-input');
  const messageList = document.getElementById('message-list');

  if(!sendBtn || !input || !messageList) return;

  input.addEventListener('input', function(){
    this.rows = 1;
    const newRows = Math.min(10, Math.ceil(this.scrollHeight / 24));
    this.rows = Math.max(1, newRows);
  });

  sendBtn.addEventListener('click', async function(){
    const text = input.value.trim();
    if(!text) return;
    const chatId = sendBtn.dataset.chatId;
    const providerId = document.getElementById('stream-provider')?.value || sendBtn.dataset.providerId;
    if(!providerId){ alert('No provider configured. Add one in Providers.'); return; }

    if(currentController){
      currentController.abort();
      currentController = null;
    }

    const personaNameEl = document.querySelector('#persona-selector .sidebar-item.active');
    const personaInitial = personaNameEl ? personaNameEl.textContent.trim()[0] : 'U';
    const userDiv = document.createElement('div');
    userDiv.className = 'message';
    userDiv.innerHTML = `
      <div class="message-avatar">${escapeHtml(personaInitial)}</div>
      <div class="message-body"><div class="message-content">${escapeHtml(text)}</div></div>
    `;
    messageList.appendChild(userDiv);
    input.value = '';
    input.rows = 1;

    const charNameEl = document.querySelector('#char-selector .sidebar-item.active');
    const charName = charNameEl ? charNameEl.textContent.trim() : 'Assistant';
    const asstDiv = document.createElement('div');
    asstDiv.className = 'message';
    asstDiv.id = 'streaming-message';
    asstDiv.innerHTML = `
      <div class="message-avatar">${escapeHtml(charName[0] || 'A')}</div>
      <div class="message-body">
        <div class="message-header">${escapeHtml(charName)}</div>
        <div class="message-content markdown-content"></div>
      </div>
    `;
    messageList.appendChild(asstDiv);
    asstDiv.scrollIntoView({behavior:'smooth'});

    sendBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');

    currentController = new AbortController();
    const signal = currentController.signal;

    const body = {
      chat_id: chatId,
      provider_id: providerId,
      user_message: text,
      temperature: parseFloat(document.getElementById('sampler-temp')?.value || 1.0),
      top_p: parseFloat(document.getElementById('sampler-top-p')?.value || 0.95),
      max_tokens: parseInt(document.getElementById('sampler-max-tokens')?.value || 1024),
      regenerate: false
    };

    try {
      const res = await fetch('/api/stream', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body),
        signal
      });

      if(!res.ok){
        const errText = await res.text();
        throw new Error(errText || 'Stream request failed');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      let messageId = null;
      let fullText = '';

      while(true){
        const {done, value} = await reader.read();
        if(done) break;
        buffer += decoder.decode(value, {stream:true});
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for(const line of lines){
          if(!line.startsWith('data: ')) continue;
          const data = line.slice(6).trim();
          if(!data) continue;
          let json;
          try{ json = JSON.parse(data); }catch(e){ continue; }
          if(json.type === 'start'){
            messageId = json.message_id;
          } else if(json.token !== undefined){
            fullText += json.token;
            const contentDiv = asstDiv.querySelector('.message-content');
            if(contentDiv) contentDiv.textContent = fullText;
          } else if(json.error){
            throw new Error(json.error);
          } else if(json.done){
            messageId = json.message_id;
          }
        }
      }

      const contentDiv = asstDiv.querySelector('.message-content');
      if(contentDiv){
        contentDiv.innerHTML = DOMPurify.sanitize(marked.parse(fullText));
      }
      if(messageId){
        asstDiv.id = 'message-' + messageId;
        asstDiv.dataset.messageId = messageId;
      }

      htmx.ajax('GET', '/partials/message-list/' + chatId, {target:'#message-list', swap:'innerHTML'});

    } catch(err){
      if(err.name !== 'AbortError'){
        const contentDiv = asstDiv.querySelector('.message-content');
        if(contentDiv){
          contentDiv.innerHTML = '<span style="color:var(--danger)">Error: ' + escapeHtml(err.message) + '</span>';
        }
      }
    } finally {
      currentController = null;
      sendBtn.classList.remove('hidden');
      stopBtn.classList.add('hidden');
    }
  });

  stopBtn.addEventListener('click', function(){
    if(currentController){
      currentController.abort();
      currentController = null;
    }
  });

  function escapeHtml(text){
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  window.editMessage = function(messageId, chatId){
    const msgEl = document.getElementById('message-' + messageId);
    if(!msgEl) return;
    const contentDiv = msgEl.querySelector('.message-content');
    const oldText = contentDiv.textContent;
    contentDiv.innerHTML = `<textarea class="w-full" rows="3" style="background:var(--surface-2);border:1px solid var(--border);color:var(--text);border-radius:6px;padding:0.5rem;font-family:inherit;">${escapeHtml(oldText)}</textarea>
    <div class="flex gap-2 mt-1"><button class="btn btn-primary btn-sm" onclick="saveEdit('${messageId}','${chatId}',this)">Save</button><button class="btn btn-secondary btn-sm" onclick="htmx.ajax('GET','/partials/message-list/${chatId}',{target:'#message-list',swap:'innerHTML'})">Cancel</button></div>`;
  };

  window.saveEdit = function(messageId, chatId, btn){
    const textarea = btn.closest('.message-content').querySelector('textarea');
    const text = textarea.value;
    fetch('/api/chats/' + chatId + '/messages/' + messageId, {
      method: 'PATCH',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({content: text})
    }).then(function(){
      htmx.ajax('GET', '/partials/message-list/' + chatId, {target:'#message-list', swap:'innerHTML'});
    });
  };

  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('.markdown-content').forEach(function(el){
      const raw = el.textContent || '';
      el.innerHTML = DOMPurify.sanitize(marked.parse(raw));
    });
  });

  document.body.addEventListener('htmx:afterSwap', function(evt){
    if(evt.detail.target.id === 'message-list'){
      evt.detail.target.querySelectorAll('.markdown-content').forEach(function(el){
        const raw = el.textContent || '';
        el.innerHTML = DOMPurify.sanitize(marked.parse(raw));
      });
    }
  });
})();