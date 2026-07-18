(function(){
  let currentController = null;
  const sendBtn = document.getElementById('send-btn');
  const stopBtn = document.getElementById('stop-btn');
  const input = document.getElementById('chat-input');
  const messageList = document.getElementById('message-list');
  const fileUpload = document.getElementById('file-upload');
  const stagingArea = document.getElementById('staging-area');

  let stagedFiles = [];

  if(!sendBtn || !input || !messageList) return;

  function renderStagingArea() {
    if (!stagingArea) return;
    stagingArea.innerHTML = '';
    stagedFiles.forEach((f, idx) => {
      const el = document.createElement('div');
      el.className = 'flex items-center gap-1 bg-surface-2 p-1 rounded border border-border text-xs relative group';
      
      let preview = '';
      if (f.type.startsWith('image/')) {
        const url = URL.createObjectURL(f);
        preview = `<img src="${url}" class="h-8 w-8 object-cover rounded" onload="URL.revokeObjectURL(this.src)">`;
      } else {
        preview = `<div class="h-8 w-8 bg-surface-3 flex items-center justify-center rounded">🎵</div>`;
      }

      el.innerHTML = `
        ${preview}
        <span class="max-w-[100px] truncate" title="${f.name}">${f.name}</span>
        <button class="absolute -top-2 -right-2 bg-danger text-white rounded-full w-4 h-4 flex items-center justify-center hidden group-hover:flex" onclick="removeStagedFile(${idx})">×</button>
      `;
      stagingArea.appendChild(el);
    });
    
    // Update button state whenever files are added/removed
    if (typeof updateSendButtonState === 'function') {
      updateSendButtonState();
    }
  }

  window.removeStagedFile = function(idx) {
    stagedFiles.splice(idx, 1);
    renderStagingArea();
  };

  if (fileUpload) {
    fileUpload.addEventListener('change', function(e) {
      if (e.target.files.length) {
        stagedFiles.push(...Array.from(e.target.files));
        renderStagingArea();
        e.target.value = ''; // reset
      }
    });
  }

  // Drag and Drop
  input.addEventListener('dragover', e => { e.preventDefault(); input.style.background = 'var(--surface-3)'; });
  input.addEventListener('dragleave', e => { e.preventDefault(); input.style.background = ''; });
  input.addEventListener('drop', e => {
    e.preventDefault();
    input.style.background = '';
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      stagedFiles.push(...Array.from(e.dataTransfer.files));
      renderStagingArea();
    }
  });

  function resizeTextarea(el) {
    el.style.height = '44px';
    if (el.value === '') {
      el.style.overflowY = 'hidden';
      return;
    }
    const scrollHeight = el.scrollHeight;
    if (scrollHeight > 44) {
      el.style.height = Math.min(250, scrollHeight) + 'px';
    }
    el.style.overflowY = scrollHeight > 250 ? 'auto' : 'hidden';
  }

  const sendIconPath = '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"></path>';
  const regenIconPath = '<path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"></path><path d="M3 3v5h5"></path>';

  function updateSendButtonState() {
    const text = input.value.trim();
    const dataList = document.getElementById('message-list-data');
    const lastRole = dataList ? dataList.getAttribute('data-last-role') : '';
    const isRegenMode = !text && stagedFiles.length === 0 && lastRole === 'user';
    
    if (isRegenMode) {
      sendBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><g>${regenIconPath}</g></svg>`;
      sendBtn.title = "Regenerate";
      sendBtn.dataset.mode = "regen";
    } else {
      sendBtn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><g>${sendIconPath}</g></svg>`;
      sendBtn.title = "Send message";
      sendBtn.dataset.mode = "send";
    }
  }

  input.addEventListener('input', function(){
    resizeTextarea(this);
    updateSendButtonState();
  });

  // Call on load to set initial state
  if (sendBtn) {
    updateSendButtonState();
  }

  window.triggerGeneration = async function(chatId, asstDiv, isRegen = false) {
    const providerId = document.getElementById('stream-provider')?.value || sendBtn.dataset.providerId;
    if(!providerId){ alert('No provider configured. Add one in Providers.'); return; }
    
    if(currentController){
      currentController.abort();
      currentController = null;
    }

    sendBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');

    currentController = new AbortController();
    const signal = currentController.signal;

    // Handle file upload if any (only on first send, not on regen)
    let attachmentIds = [];
    if (!isRegen && stagedFiles.length > 0) {
      const formData = new FormData();
      stagedFiles.forEach(f => formData.append('files', f));
      try {
        const uploadRes = await fetch(`/api/chats/${chatId}/attachments`, {
          method: 'POST',
          body: formData
        });
        if (uploadRes.ok) {
          const data = await uploadRes.json();
          attachmentIds = data.attachments.map(a => a.id);
        }
      } catch (e) {
        console.error("Upload failed", e);
      }
      stagedFiles = [];
      renderStagingArea();
    }

    const body = {
      chat_id: chatId,
      provider_id: providerId,
      user_message: window._tempUserMessage || "", // passed explicitly
      samplers: window.getActiveSamplers ? window.getActiveSamplers() : {},
      regenerate: isRegen,
      attachment_ids: attachmentIds
    };
    
    window._tempUserMessage = ""; // clear

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
            if(contentDiv) {
              // Preserve state of any opened reasoning blocks
              const openStates = new Set();
              contentDiv.querySelectorAll('details.reasoning[open]').forEach(d => {
                if (d.dataset.thinkId) openStates.add(d.dataset.thinkId);
              });
              
              contentDiv.innerHTML = renderMessage(fullText);
              
              // Restore open states
              openStates.forEach(id => {
                const el = contentDiv.querySelector(`details.reasoning[data-think-id="${id}"]`);
                if (el) el.setAttribute('open', '');
              });
            }
          } else if(json.error){
            throw new Error(json.error);
          } else if(json.done){
            messageId = json.message_id;
          }
        }
      }

      const contentDiv = asstDiv.querySelector('.message-content');
      if(contentDiv){
        // Preserve state one last time for final render
        const openStates = new Set();
        contentDiv.querySelectorAll('details.reasoning[open]').forEach(d => {
          if (d.dataset.thinkId) openStates.add(d.dataset.thinkId);
        });
        
        contentDiv.innerHTML = renderMessage(fullText);
        
        openStates.forEach(id => {
          const el = contentDiv.querySelector(`details.reasoning[data-think-id="${id}"]`);
          if (el) el.setAttribute('open', '');
        });
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
  };

  sendBtn.addEventListener('click', async function(){
    const chatId = sendBtn.dataset.chatId;
    const providerId = document.getElementById('stream-provider')?.value || sendBtn.dataset.providerId;
    
    if (sendBtn.dataset.mode === 'regen') {
      if(!providerId){ alert('No provider configured. Add one in Providers.'); return; }
      
      const dataList = document.getElementById('message-list-data');
      const charName = dataList ? dataList.getAttribute('data-char-name') : 'Assistant';
      const charImagePath = dataList ? dataList.getAttribute('data-char-image') : '';
      const avatarHtml = charImagePath ? `<img src="/${charImagePath}" alt="">` : escapeHtml(charName[0] || 'A');

      const asstDiv = document.createElement('div');
      asstDiv.className = 'message';
      asstDiv.id = 'streaming-message';
      asstDiv.innerHTML = `
        <div class="message-avatar">${avatarHtml}</div>
        <div class="message-body">
          <div class="message-header">${escapeHtml(charName)}</div>
          <div class="message-content markdown-content"></div>
        </div>
      `;
      messageList.appendChild(asstDiv);
      asstDiv.scrollIntoView({behavior:'smooth'});

      window.triggerGeneration(chatId, asstDiv, false); // pass false so we create a NEW message, not overwrite last
      return;
    }

    const text = input.value.trim();
    if(!text && stagedFiles.length === 0) return;
    if(!providerId){ alert('No provider configured. Add one in Providers.'); return; }

    const personaNameEl = document.querySelector('#persona-selector .sidebar-item.active');
    const personaInitial = personaNameEl ? personaNameEl.textContent.trim()[0] : 'U';
    const userDiv = document.createElement('div');
    userDiv.className = 'message';
    
    // Quick preview of attachments
    let attachPreview = '';
    if (stagedFiles.length > 0) {
      attachPreview = '<div class="flex gap-2 flex-wrap mb-2">' + stagedFiles.map(f => {
        if (f.type.startsWith('image/')) return `<img src="${URL.createObjectURL(f)}" class="h-24 rounded object-cover border border-border cursor-pointer" onclick="openLightbox(this.src)">`;
        return `<div class="h-16 bg-surface-3 px-2 rounded flex items-center text-xs">🎵 ${f.name}</div>`;
      }).join('') + '</div>';
    }

    userDiv.innerHTML = `
      <div class="message-avatar">${escapeHtml(personaInitial)}</div>
      <div class="message-body">
        ${attachPreview}
        <div class="message-content">${escapeHtml(text)}</div>
      </div>
    `;
    messageList.appendChild(userDiv);
    
    window._tempUserMessage = text;
    
    input.value = '';
    resizeTextarea(input);

    const dataList = document.getElementById('message-list-data');
    const charName = dataList ? dataList.getAttribute('data-char-name') : 'Assistant';
    const charImagePath = dataList ? dataList.getAttribute('data-char-image') : '';
    const avatarHtml = charImagePath ? `<img src="/${charImagePath}" alt="">` : escapeHtml(charName[0] || 'A');

    const asstDiv = document.createElement('div');
    asstDiv.className = 'message';
    asstDiv.id = 'streaming-message';
    asstDiv.innerHTML = `
      <div class="message-avatar">${avatarHtml}</div>
      <div class="message-body">
        <div class="message-header">${escapeHtml(charName)}</div>
        <div class="message-content markdown-content"></div>
      </div>
    `;
    messageList.appendChild(asstDiv);
    asstDiv.scrollIntoView({behavior:'smooth'});

    window.triggerGeneration(chatId, asstDiv, false);
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

  function extractThoughtsSafely(text) {
    const codeBlocks = [];
    let processed = text.replace(/```[\s\S]*?(?:```|$)/g, match => {
      codeBlocks.push(match);
      return `%%%PYVERN_CODE_${codeBlocks.length - 1}%%%`;
    });
    
    processed = processed.replace(/`[^`\n]*`/g, match => {
      codeBlocks.push(match);
      return `%%%PYVERN_CODE_${codeBlocks.length - 1}%%%`;
    });
    
    const thoughts = [];
    processed = processed.replace(/<think>([\s\S]*?)(?:<\/think>|$)/g, function(match, p1) {
      const isClosed = match.includes('</think>');
      thoughts.push({ content: p1, isClosed: isClosed });
      return `\n\n%%%THINK_BLOCK_${thoughts.length - 1}%%%\n\n`;
    });
    
    for (let j = 0; j < codeBlocks.length; j++) {
      const marker = `%%%PYVERN_CODE_${j}%%%`;
      processed = processed.split(marker).join(codeBlocks[j]);
      for (let t of thoughts) {
          t.content = t.content.split(marker).join(codeBlocks[j]);
      }
    }
    
    return { thoughts, processed };
  }

  function renderMessage(text) {
    if (!text) return "";
    
    // 1. Extract and protect thinking blocks avoiding code blocks
    const extracted = extractThoughtsSafely(text);
    const thoughts = extracted.thoughts;
    let processed = extracted.processed;
    
    // 2. Parse Markdown and Sanitize the rest
    marked.use({ breaks: true });
    let html = DOMPurify.sanitize(marked.parse(processed));
    
    // 3. Restore thinking blocks with exact line breaks
    for (let i = 0; i < thoughts.length; i++) {
      const t = thoughts[i];
      // Escape HTML entities, then replace \n with <br> to preserve line breaks exactly
      const safeInner = escapeHtml(t.content).trim().replace(/\n/g, '<br>');
      // Use a custom attribute to track if the user has manually opened it during streaming
      const detailsHtml = `<details class="reasoning" data-think-id="${i}"><summary>Thought Process</summary><div class="reasoning-content">${safeInner}</div></details>`;
      
      // DOMPurify + marked might wrap the placeholder in <p> tags, so we catch them
      const regex = new RegExp(`<p>%%%THINK_BLOCK_${i}%%%<\\/p>|%%%THINK_BLOCK_${i}%%%`, 'g');
      html = html.replace(regex, () => detailsHtml);
    }
    
    return html;
  }

  window.editMessage = async function(messageId, chatId){
    try {
      const res = await fetch(`/api/chats/${chatId}/messages/${messageId}`);
      if (!res.ok) throw new Error("Failed to load message");
      const data = await res.json();
      const rawText = data.content;

      // Extract thought process safely
      const extracted = extractThoughtsSafely(rawText);
      let thoughtText = extracted.thoughts.map(t => t.content.trim()).join('\n\n');
      
      let messageText = extracted.processed;
      for (let i = 0; i < extracted.thoughts.length; i++) {
         messageText = messageText.replace(new RegExp(`\\s*%%%THINK_BLOCK_${i}%%%\\s*`), '\n\n');
      }
      messageText = messageText.trim();

      document.getElementById('edit-msg-id').value = messageId;
      document.getElementById('edit-msg-chat-id').value = chatId;

      const thoughtContainer = document.getElementById('edit-msg-thought-container');
      const thoughtInput = document.getElementById('edit-msg-thought');
      if (thoughtText) {
        thoughtInput.value = thoughtText;
        thoughtContainer.style.display = 'block';
      } else {
        thoughtInput.value = "";
        thoughtContainer.style.display = 'none';
      }

      document.getElementById('edit-msg-content').value = messageText;
      
      // We assume openModal exists globally from base.html/chat.html
      if(window.openModal) window.openModal('modal-edit-message');
      else document.getElementById('modal-edit-message').style.display = 'grid';

    } catch (err) {
      alert("Error editing message: " + err.message);
    }
  };

  window.saveMessageEdit = async function(){
    const messageId = document.getElementById('edit-msg-id').value;
    const chatId = document.getElementById('edit-msg-chat-id').value;
    
    let text = document.getElementById('edit-msg-content').value.trim();
    
    const thoughtContainer = document.getElementById('edit-msg-thought-container');
    if (thoughtContainer.style.display !== 'none') {
      const thoughtText = document.getElementById('edit-msg-thought').value.trim();
      if (thoughtText) {
        text = `<think>\n${thoughtText}\n</think>\n\n${text}`;
      }
    }

    try {
      await fetch(`/api/chats/${chatId}/messages/${messageId}`, {
        method: 'PATCH',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify({content: text})
      });
      
      if(window.closeModal) window.closeModal('modal-edit-message');
      else document.getElementById('modal-edit-message').style.display = 'none';
      
      htmx.ajax('GET', '/partials/message-list/' + chatId, {target:'#message-list', swap:'innerHTML'});
    } catch(err) {
      alert("Failed to save edit: " + err.message);
    }
  };

  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('.markdown-content').forEach(function(el){
      const raw = el.textContent || '';
        el.innerHTML = renderMessage(raw);
    });
    
    // Restore provider from localStorage
    const savedProvider = localStorage.getItem('pyvern-provider-id');
    if (savedProvider) {
      const select = document.getElementById('stream-provider');
      if (select && select.querySelector(`option[value="${savedProvider}"]`)) {
        select.value = savedProvider;
        const sendBtn = document.getElementById('send-btn');
        if(sendBtn) sendBtn.dataset.providerId = savedProvider;
      }
    }
  });

  // Global event delegation to handle details toggle via mousedown
  // This bypasses the click event cancellation caused by rapid innerHTML updates during streaming
  document.addEventListener('mousedown', function(e) {
    if (e.target && e.target.tagName === 'SUMMARY') {
      const details = e.target.closest('details.reasoning');
      if (details) {
        e.preventDefault();
        if (details.hasAttribute('open')) {
          details.removeAttribute('open');
        } else {
          details.setAttribute('open', '');
        }
      }
    }
  });

  // Prevent default click behavior on summary to avoid double-toggling if a click does go through
  document.addEventListener('click', function(e) {
    if (e.target && e.target.tagName === 'SUMMARY' && e.target.closest('details.reasoning')) {
      e.preventDefault();
    }
  });

  window.saveSampler = function(key, value) {
    localStorage.setItem(key, value);
  };

  document.body.addEventListener('htmx:afterSwap', function(evt){
    if(evt.detail.target.id === 'message-list'){
      evt.detail.target.querySelectorAll('.markdown-content').forEach(function(el){
        const raw = el.textContent || '';
      el.innerHTML = renderMessage(raw);
      });
    }
  });
})();