(function(){
  const SVG_CLOSE = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';
  let currentController = null;
  const sendBtn = document.getElementById('send-btn');
  const stopBtn = document.getElementById('stop-btn');
  const input = document.getElementById('chat-input');
  const messageList = document.getElementById('message-list');
  const fileUpload = document.getElementById('file-upload');
  const stagingArea = document.getElementById('staging-area');

  let stagedFiles = [];

  let autoScroll = true;
  let scrollSentinel = null;
  let chatCenterEl = null;

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
        const cropSvg = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6.13 1L6 16a2 2 0 0 0 2 2h15"></path><path d="M1 6.13L16 6a2 2 0 0 1 2 2v15"></path></svg>`;
        const cropBtn = `<button class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-black/70 text-white rounded-full w-6 h-6 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity z-10 hover:bg-black/90" onclick="cropStagedImage(${idx})" title="Crop">${cropSvg}</button>`;
        
        preview = `
          <div class="relative h-8 w-8 flex-shrink-0">
            <img src="${url}" class="h-full w-full object-cover rounded" onload="URL.revokeObjectURL(this.src)">
            ${cropBtn}
          </div>
        `;
      } else {
        preview = `<div class="h-8 w-8 bg-surface-3 flex items-center justify-center rounded flex-shrink-0">${SVG_MUSIC}</div>`;
      }

      el.innerHTML = `
        ${preview}
        <span class="max-w-[100px] truncate" title="${f.name}">${f.name}</span>
        <button class="text-danger hover:text-white hover:bg-danger rounded w-5 h-5 flex items-center justify-center ml-1 transition-colors z-20" onclick="removeStagedFile(${idx})" title="Remove">${SVG_CLOSE}</button>
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
  
  window.cropStagedImage = function(idx) {
    const file = stagedFiles[idx];
    if (!file || !file.type.startsWith('image/')) return;
    if (typeof openCropModal !== 'function') return;
    
    openCropModal(file, (croppedBlob) => {
        // Replace the staged file with the new cropped blob
        const newFile = new File([croppedBlob], file.name, { type: 'image/png' });
        stagedFiles[idx] = newFile;
        renderStagingArea();
    }, { aspectRatio: NaN }); // Freeform crop
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

  // Paste handling
  window.addEventListener('paste', e => {
      if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length > 0) {
          // If the user pastes an image, grab it
          const newFiles = Array.from(e.clipboardData.files).filter(f => f.type.startsWith('image/'));
          if (newFiles.length > 0) {
              stagedFiles.push(...newFiles);
              renderStagingArea();
              e.preventDefault();
          }
      }
  });

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

  async function refreshMessagesAfterStream(chatId, userMsgId, asstMsgId) {
    const resp = await fetch('/partials/message-list/' + chatId);
    if (!resp.ok) return;
    const html = await resp.text();
    const doc = new DOMParser().parseFromString(html, 'text/html');

    const newSentinel = doc.getElementById('message-list-data');
    const oldSentinel = document.getElementById('message-list-data');
    if (newSentinel && oldSentinel) {
      oldSentinel.replaceWith(newSentinel);
    }

    const toolbar = document.getElementById('delete-toolbar');
    const inDeleteMode = toolbar && !toolbar.classList.contains('hidden');

    const ids = [userMsgId, asstMsgId].filter(Boolean);
    for (const id of ids) {
      const newMsg = doc.getElementById('message-' + id);
      const oldMsg = document.getElementById('message-' + id);
      if (newMsg && oldMsg) {
        newMsg.style.setProperty('animation', 'none', 'important');
        oldMsg.replaceWith(newMsg);
        htmx.process(newMsg);
        newMsg.querySelectorAll('.markdown-content:not(.processed)').forEach(function(el) {
          el.innerHTML = renderMessage(el.textContent || '');
          el.classList.add('processed');
        });
        if (inDeleteMode) {
          const cb = newMsg.querySelector('.delete-mode-checkbox');
          if (cb) cb.classList.remove('hidden');
          const actions = newMsg.querySelector('.normal-mode-actions');
          if (actions) actions.classList.add('hidden');
        }
      }
    }

    if (typeof updateSendButtonState === 'function') {
      updateSendButtonState();
    }

    ensureSentinelAndObserver();
  }

  window.triggerGeneration = async function(chatId, asstDiv, isRegen = false) {
    const providerId = sendBtn.dataset.providerId;
    if(!providerId){ alert('No provider configured. Add one in Providers.'); return; }
    
    // Hide error toast on new generation
    const errorToast = document.getElementById('error-toast');
    if (errorToast) errorToast.classList.add('hidden');
    
    if(currentController){
      currentController.abort();
      currentController = null;
    }

    sendBtn.classList.add('hidden');
    stopBtn.classList.remove('hidden');

    const contentDiv = asstDiv.querySelector('.message-content');
    if (contentDiv) {
      contentDiv.innerHTML = '<div class="message-spinner"></div>';
    }

    currentController = new AbortController();
    const signal = currentController.signal;

    // Handle file upload if any (only on first send, not on regen)
    let attachmentIds = [];
    if (!isRegen && stagedFiles.length > 0) {
      const filesToUpload = [...stagedFiles];
      const formData = new FormData();
      filesToUpload.forEach(f => formData.append('files', f));
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
      stagedFiles = stagedFiles.filter(f => !filesToUpload.includes(f));
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
      let userMessageId = null;
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
            userMessageId = json.user_message_id;
            // Set user message div ID so the OOB swap can match it
            if(json.user_message_id){
              const userDiv = asstDiv.previousElementSibling;
              if(userDiv && userDiv.classList.contains('message')){
                userDiv.id = 'message-' + json.user_message_id;
              }
            }
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

              if (autoScroll && scrollSentinel) {
                scrollSentinel.scrollIntoView({behavior: 'instant'});
              }
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

      await refreshMessagesAfterStream(chatId, userMessageId, messageId);

    } catch(err){
      if(err.name !== 'AbortError'){
        // Show error toast
        const errorToast = document.getElementById('error-toast');
        const errorToastText = document.getElementById('error-toast-text');
        if (errorToast && errorToastText) {
          errorToastText.innerText = err.message;
          errorToast.classList.remove('hidden');
        }
        
        // Remove empty assistant message from UI if failed immediately
        if (!fullText.trim() && asstDiv.parentNode) {
          asstDiv.remove();
        }

        // Force a re-fetch of the message list so the last-role syncs with the DB (user message was saved)
        await refreshMessagesAfterStream(chatId, userMessageId, messageId);
      }
    } finally {
      currentController = null;
      sendBtn.classList.remove('hidden');
      stopBtn.classList.add('hidden');
    }
  };

  sendBtn.addEventListener('click', async function(){
    const chatId = sendBtn.dataset.chatId;
    const providerId = sendBtn.dataset.providerId;
    
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
          <div class="message-content markdown-content processed"></div>
        </div>
      `;
      messageList.insertBefore(asstDiv, scrollSentinel);
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
        return `<div class="h-16 bg-surface-3 px-2 rounded flex items-center text-xs">${SVG_MUSIC} ${f.name}</div>`;
      }).join('') + '</div>';
    }

    userDiv.innerHTML = `
      <div class="message-avatar">${escapeHtml(personaInitial)}</div>
      <div class="message-body">
        ${attachPreview}
        <div class="message-content">${escapeHtml(text)}</div>
      </div>
    `;
    messageList.insertBefore(userDiv, scrollSentinel);
    
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
        <div class="message-content markdown-content processed"></div>
      </div>
    `;
    messageList.insertBefore(asstDiv, scrollSentinel);
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

    // Remove thought signature completely from UI
    processed = processed.replace(/<thought_signature>([\s\S]*?)(?:<\/thought_signature>|$)/g, '');
    
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
      
      window.currentEditAttachments = data.attachments || [];
      renderEditModalAttachments();
      
      // We assume openModal exists globally from base.html/chat.html
      if(window.openModal) window.openModal('modal-edit-message');
      else document.getElementById('modal-edit-message').style.display = 'grid';

    } catch (err) {
      alert("Error editing message: " + err.message);
    }
  };

  window.renderEditModalAttachments = function() {
      const container = document.getElementById('edit-msg-attachments');
      if (!container) return;
      
      container.innerHTML = '';
      if (window.currentEditAttachments.length === 0) {
          container.innerHTML = '<div class="text-xs text-muted w-full text-center italic py-2">No attachments</div>';
          return;
      }
      
      window.currentEditAttachments.forEach((att, idx) => {
          const el = document.createElement('div');
          el.className = 'relative group flex-shrink-0';
          
          if (att.mime_type.startsWith('image/')) {
              el.innerHTML = `
                  <img src="/${att.file_path}" class="h-16 w-16 rounded object-cover border border-border" alt="attachment">
                  <button class="absolute -top-2 -right-2 bg-danger text-white rounded-full w-4 h-4 flex items-center justify-center text-[10px] hidden group-hover:flex z-10" onclick="deleteModalAttachment(${idx})" title="Delete">${SVG_CLOSE}</button>
              `;
          } else {
              el.innerHTML = `
                  <div class="h-16 w-16 bg-surface-3 rounded border border-border flex items-center justify-center">${SVG_MUSIC}</div>
                  <button class="absolute -top-2 -right-2 bg-danger text-white rounded-full w-4 h-4 flex items-center justify-center text-[10px] hidden group-hover:flex z-10" onclick="deleteModalAttachment(${idx})" title="Delete">${SVG_CLOSE}</button>
              `;
          }
          container.appendChild(el);
      });
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
        body: JSON.stringify({
            content: text,
            attachment_ids: window.currentEditAttachments.map(a => a.id)
        })
      });
      
      if(window.closeModal) window.closeModal('modal-edit-message');
      else document.getElementById('modal-edit-message').style.display = 'none';
      
      htmx.ajax('GET', '/partials/message-list/' + chatId, {target:'#message-list', swap:'innerHTML'});
    } catch(err) {
      alert("Failed to save edit: " + err.message);
    }
  };

  function ensureSentinelAndObserver() {
    const ml = document.getElementById('message-list');
    const cc = document.querySelector('.chat-center');
    if (!ml || !cc) return;

    chatCenterEl = cc;

    let s = document.getElementById('scroll-sentinel');
    if (!s) {
      s = document.createElement('div');
      s.id = 'scroll-sentinel';
      s.style.height = '1px';
      ml.appendChild(s);
    } else if (ml.lastChild !== s) {
      ml.appendChild(s);
    }
    scrollSentinel = s;

    if (window._scrollObserver) window._scrollObserver.disconnect();
    window._scrollObserver = new IntersectionObserver(function(_ref) {
      autoScroll = _ref[0].isIntersecting;
    }, { root: cc, threshold: 0 });
    window._scrollObserver.observe(s);
  }

  document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('.markdown-content').forEach(function(el){
      const raw = el.textContent || '';
      el.innerHTML = renderMessage(raw);
      el.classList.add('processed');
    });

    ensureSentinelAndObserver();

    var navEntries = performance.getEntriesByType('navigation');
    if (navEntries.length > 0 && navEntries[0].type === 'navigate') {
      requestAnimationFrame(function() {
        requestAnimationFrame(function() {
          var s = document.getElementById('scroll-sentinel');
          if (s) s.scrollIntoView({block: 'end'});
        });
      });
    }

    document.getElementById('message-list')?.classList.add('ready');
    
    // Restore provider from localStorage
    const savedProvider = localStorage.getItem('pyvern-provider-id');
    if (savedProvider) {
      const sendBtn = document.getElementById('send-btn');
      if(sendBtn) sendBtn.dataset.providerId = savedProvider;
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
        el.classList.add('processed');
      });
      // Ensure the send button correctly updates its mode after DOM changes (like deletions or errors)
    if (typeof updateSendButtonState === 'function') {
      updateSendButtonState();
    }

    ensureSentinelAndObserver();
  }
  });
})();
  // --- DELETE MODE & BULK DELETE ---
  let lastDeleteSelection = [];
  
  window.enterDeleteMode = function(startMessageId) {
    document.getElementById('standard-input-container').classList.add('hidden');
    document.getElementById('delete-toolbar').classList.remove('hidden');
    document.getElementById('delete-toolbar').classList.add('flex');
    
    // Hide normal actions, show checkboxes
    document.querySelectorAll('.normal-mode-actions').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('.delete-mode-checkbox').forEach(el => el.classList.remove('hidden'));
    
    if (startMessageId) {
      // Pre-select the clicked message and all following messages
      let foundStart = false;
      document.querySelectorAll('.message').forEach(msgDiv => {
        if (msgDiv.dataset.messageId === startMessageId) foundStart = true;
        const cb = msgDiv.querySelector('.msg-select-checkbox');
        if (cb) cb.checked = foundStart;
      });
    } else {
      // Restore previous selection if re-entering after DOM swap
      document.querySelectorAll('.msg-select-checkbox').forEach(cb => {
         if (lastDeleteSelection.includes(cb.value)) cb.checked = true;
      });
    }
    
    updateDeleteSelection();
  };

  window.exitDeleteMode = function() {
    document.getElementById('delete-toolbar').classList.remove('flex');
    document.getElementById('delete-toolbar').classList.add('hidden');
    document.getElementById('standard-input-container').classList.remove('hidden');
    
    document.querySelectorAll('.normal-mode-actions').forEach(el => el.classList.remove('hidden'));
    document.querySelectorAll('.delete-mode-checkbox').forEach(el => el.classList.add('hidden'));
    
    document.querySelectorAll('.msg-select-checkbox').forEach(cb => cb.checked = false);
    lastDeleteSelection = [];
  };

  window.updateDeleteSelection = function() {
    const selectedCbs = document.querySelectorAll('.msg-select-checkbox:checked');
    lastDeleteSelection = Array.from(selectedCbs).map(cb => cb.value);
    const countEl = document.getElementById('delete-selected-count');
    if (countEl) countEl.textContent = lastDeleteSelection.length;
  };

  window.bulkDeleteSelected = async function(chatId) {
    const selected = Array.from(document.querySelectorAll('.msg-select-checkbox:checked')).map(cb => cb.value);
    if (selected.length === 0) {
        exitDeleteMode();
        return;
    }
    
    window.customConfirm(`Delete ${selected.length} message(s)?`, async () => {
        try {
            const res = await fetch(`/api/chats/${chatId}/messages/bulk_delete`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ message_ids: selected })
            });
            if (res.ok) {
                htmx.ajax('GET', `/partials/message-list/${chatId}`, {target: '#message-list', swap: 'innerHTML'});
            } else {
                alert('Failed to delete messages');
            }
        } catch (e) {
            console.error(e);
        }
        
        exitDeleteMode();
    });
  };

  // --- EXISTING MESSAGE ATTACHMENTS ---
  window.uploadMessageAttachment = async function(inputEl) {
      if (!inputEl.files.length) return;
      const chatId = document.getElementById('edit-msg-chat-id').value;
      if (!chatId) return;
      
      const formData = new FormData();
      Array.from(inputEl.files).forEach(f => formData.append('files', f));
      
      try {
          const res = await fetch(`/api/chats/${chatId}/attachments`, {
              method: 'POST',
              body: formData
          });
          if (res.ok) {
              const data = await res.json();
              window.currentEditAttachments.push(...data.attachments);
              renderEditModalAttachments();
          } else {
              alert("Failed to upload attachment");
          }
      } catch(err) {
          console.error(err);
      } finally {
          inputEl.value = ''; // Reset file input
      }
  };

  window.deleteModalAttachment = function(idx) {
      window.currentEditAttachments.splice(idx, 1);
      renderEditModalAttachments();
  };

  // Re-apply delete mode if DOM is swapped while active
  document.body.addEventListener('htmx:afterSettle', function(e) {
      if (e.target.id === 'message-list') {
          const toolbar = document.getElementById('delete-toolbar');
          if (toolbar && !toolbar.classList.contains('hidden')) {
              enterDeleteMode();
          }
      }
  });

