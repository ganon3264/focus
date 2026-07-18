(function () {
  window.editMessage = async function (messageId, chatId) {
    try {
      const res = await fetch(window.api.chatMessage(chatId, messageId));
      if (!res.ok) throw new Error('Failed to load message');
      const data = await res.json();
      const rawText = data.content;

      const extracted = window.extractThoughtsSafely(rawText);
      let thoughtText = extracted.thoughts.map((t) => t.content.trim()).join('\n\n');

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
        thoughtInput.value = '';
        thoughtContainer.style.display = 'none';
      }

      document.getElementById('edit-msg-content').value = messageText;

      window.currentEditAttachments = data.attachments || [];
      window.renderEditModalAttachments();

      if (window.openModal) window.openModal('modal-edit-message');
      else document.getElementById('modal-edit-message').classList.remove('hidden');
    } catch (err) {
      alert('Error editing message: ' + err.message);
    }
  };

  window.renderEditModalAttachments = function () {
    const container = document.getElementById('edit-msg-attachments');
    if (!container) return;

    container.innerHTML = '';
    if (window.currentEditAttachments.length === 0) {
      container.innerHTML =
        '<div class="text-xs text-muted w-full text-center italic py-2">No attachments</div>';
      return;
    }

    window.currentEditAttachments.forEach((att, idx) => {
      const el = document.createElement('div');
      el.className = 'relative group shrink-0';

      if (att.mime_type.startsWith('image/')) {
        el.innerHTML = `
          <img src="/${att.file_path}" class="h-16 w-16 rounded object-cover border border-border" alt="attachment">
          <button class="absolute -top-2 -right-2 bg-danger text-white rounded-full w-4 h-4 flex items-center justify-center text-[10px] hidden group-hover:flex z-10" onclick="window.deleteModalAttachment(${idx})" title="Delete">${window.getSvgSprite('close', 16)}</button>
        `;
      } else {
        el.innerHTML = `
          <div class="h-16 w-16 bg-surface-3 rounded border border-border flex items-center justify-center">${window.getSvgSprite('music', 24)}</div>
          <button class="absolute -top-2 -right-2 bg-danger text-white rounded-full w-4 h-4 flex items-center justify-center text-[10px] hidden group-hover:flex z-10" onclick="window.deleteModalAttachment(${idx})" title="Delete">${window.getSvgSprite('close', 16)}</button>
        `;
      }
      container.appendChild(el);
    });
  };

  window.saveMessageEdit = async function () {
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
      await fetch(window.api.chatMessage(chatId, messageId), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: text,
          attachment_ids: window.currentEditAttachments.map((a) => a.id),
        }),
      });

      if (window.closeModal) window.closeModal('modal-edit-message');
      else document.getElementById('modal-edit-message').classList.add('hidden');

      if (typeof refreshSingleMessage === 'function') {
        refreshSingleMessage(chatId, messageId);
      } else {
        htmx.ajax('GET', window.api.partials.messageList(chatId), {
          target: '#message-list',
          swap: 'innerHTML',
        });
        if (window._refreshChatList) window._refreshChatList(chatId);
      }
    } catch (err) {
      alert('Failed to save edit: ' + err.message);
    }
  };

  window.uploadMessageAttachment = async function (inputEl) {
    if (!inputEl.files.length) return;
    await window.uploadMessageAttachmentFiles(Array.from(inputEl.files));
    inputEl.value = '';
  };

  window.uploadMessageAttachmentFiles = async function (files) {
    if (!files.length) return;
    const chatId = document.getElementById('edit-msg-chat-id').value;
    if (!chatId) return;

    const formData = new FormData();
    files.forEach((f) => formData.append('files', f));

    try {
      const res = await fetch(window.api.chatAttachments(chatId), {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        window.currentEditAttachments.push(...data.attachments);
        window.renderEditModalAttachments();
      } else {
        alert('Failed to upload attachment');
      }
    } catch (err) {
      console.error(err);
    }
  };

  window.deleteModalAttachment = function (idx) {
    window.currentEditAttachments.splice(idx, 1);
    window.renderEditModalAttachments();
  };

  if (typeof window.setupDropZone === 'function') {
    window.setupDropZone('#edit-msg-attachments', window.uploadMessageAttachmentFiles);
  }
})();
