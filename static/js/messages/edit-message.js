(function () {
  function buildEditBlocks(content, toolCalls, reasoning) {
    var blocks = [];
    var toolCallsRendered = false;

    if (reasoning) {
      blocks.push({ type: 'reasoning', content: reasoning.trim() });
    }

    var parts = (content || '').split('%%%TOOL_BOUNDARY%%%');

    for (var pi = 0; pi < parts.length; pi++) {
      var text = parts[pi].trim();
      if (text) {
        blocks.push({ type: 'text', content: text });
      }

      if (pi < parts.length - 1) {
        var calls = null;
        if (!toolCallsRendered && toolCalls && toolCalls.length > 0) {
          calls = toolCalls;
          toolCallsRendered = true;
        }
        blocks.push({ type: 'tool_boundary', calls: calls });
      }
    }

    return blocks;
  }

  function renderToolCallCard(tc) {
    var imgHtml = '';
    var imgSrc = tc.image_data || tc.image_url || '';
    if (imgSrc) {
      imgHtml = '<img src="' + window.escapeHtml(imgSrc) + '" class="max-w-full h-auto rounded mt-2" />';
    }
    var card = document.createElement('details');
    card.className = 'details tool-call';
    card.innerHTML =
      '<summary>' +
      (window.getSvgSprite('chevron-right', 12) || '').replace('<svg', '<svg class="w-3 h-3 chevron"') +
      '<code class="font-bold">' + window.escapeHtml(tc.function.name) + '</code>' +
      '<span class="truncate max-w-[300px]">' + window.escapeHtml(tc.function.arguments || '') + '</span>' +
      '</summary>' +
      '<div class="tool-result-body"><pre class="whitespace-pre-wrap break-all">' + window.escapeHtml(tc.result || '') + '</pre>' + imgHtml + '</div>';
    return card;
  }

  function autoResizeTextarea(ta) {
    var lines = (ta.value || '').split('\n').length;
    ta.rows = Math.max(3, Math.min(lines, 20));
  }

  function createEditTextarea(idx, bgVar, content) {
    var ta = document.createElement('textarea');
    ta.className = 'edit-block-ta';
    ta.id = 'edit-msg-ta-' + idx;
    ta.setAttribute('data-block-idx', idx);
    ta.style.background = 'var(' + bgVar + ')';
    ta.rows = 3;
    ta.value = content || '';
    autoResizeTextarea(ta);

    var wrapper = document.createElement('div');
    wrapper.className = 'textarea-wrapper';
    wrapper.appendChild(ta);

    var tpl = document.getElementById('edit-msg-expand-btn');
    if (tpl) {
      var btn = tpl.content.cloneNode(true).firstElementChild;
      btn.setAttribute('data-target-id', ta.id);
      btn.setAttribute('data-expander-title', 'Edit Block');
      wrapper.appendChild(btn);
    }

    return wrapper;
  }

  function renderEditBlocks(blocks) {
    var container = document.getElementById('edit-msg-blocks');
    if (!container) return;
    container.innerHTML = '';

    for (var i = 0; i < blocks.length; i++) {
      var blk = blocks[i];

      if (blk.type === 'reasoning') {
        var details = document.createElement('details');
        details.className = 'details reasoning-block';
        details.innerHTML =
          '<summary>' +
          (window.getSvgSprite('chevron-right', 12) || '').replace('<svg', '<svg class="w-3 h-3 chevron"') +
          '<span class="text-xs text-muted">Reasoning</span>' +
          '</summary>' +
          '<div style="margin-top:0.5rem"></div>';
        container.appendChild(details);
        var wrapper = details.querySelector('div');
        wrapper.appendChild(createEditTextarea(i, '--surface-3', blk.content));
      } else if (blk.type === 'text') {
        container.appendChild(createEditTextarea(i, '--surface-2', blk.content));
      } else if (blk.type === 'tool_boundary') {
        if (blk.calls && blk.calls.length > 0) {
          var tcSection = document.createElement('div');
          tcSection.className = 'tool-calls-section';
          for (var c = 0; c < blk.calls.length; c++) {
            tcSection.appendChild(renderToolCallCard(blk.calls[c]));
          }
          container.appendChild(tcSection);
        } else {
          var sep = document.createElement('div');
          sep.style.cssText = 'height:0;border-bottom:1px solid var(--border);margin:0.25rem 0;opacity:0.4';
          container.appendChild(sep);
        }
      }
    }
  }

  window.editMessage = async function (messageId, chatId) {
    try {
      var res = await fetch(window.api.chatMessage(chatId, messageId));
      if (!res.ok) throw new Error('Failed to load message');
      var data = await res.json();

      var blocks = buildEditBlocks(data.content, data.tool_calls, data.reasoning);
      window._editBlocks = blocks;

      document.getElementById('edit-msg-id').value = messageId;
      document.getElementById('edit-msg-chat-id').value = chatId;

      renderEditBlocks(blocks);

      window.currentEditAttachments = data.attachments || [];
      window.renderEditModalAttachments();

      if (window.openModal) window.openModal('modal-edit-message');
      else document.getElementById('modal-edit-message').classList.remove('hidden');
    } catch (err) {
      alert('Error editing message: ' + err.message);
    }
  };

  window.renderEditModalAttachments = function () {
    var container = document.getElementById('edit-msg-attachments');
    if (!container) return;

    container.innerHTML = '';
    if (window.currentEditAttachments.length === 0) {
      container.innerHTML =
        '<div class="text-xs text-muted w-full text-center italic py-2">No attachments</div>';
      return;
    }

    window.currentEditAttachments.forEach(function (att, idx) {
      var thumbnail = window.createMediaThumbnail({
        src: att.file_path || '',
        mimeType: att.mime_type,
        size: 64,
        onDelete: function () {
          window.deleteModalAttachment(idx);
        },
      });

      var wrapper = document.createElement('div');
      wrapper.className = 'relative group shrink-0';
      thumbnail.style.width = '64px';
      thumbnail.style.height = '64px';

      var deleteBtn = thumbnail.querySelector('button');
      if (deleteBtn) {
        deleteBtn.className =
          'absolute -top-2 -right-2 bg-danger text-white rounded-full w-4 h-4 flex items-center justify-center text-[10px] hidden group-hover:flex z-10';
        deleteBtn.innerHTML = window.getSvgSprite('close', 16);
      }

      wrapper.appendChild(thumbnail);
      container.appendChild(wrapper);
    });
  };

  window.saveMessageEdit = async function () {
    var messageId = document.getElementById('edit-msg-id').value;
    var chatId = document.getElementById('edit-msg-chat-id').value;
    var blocks = window._editBlocks || [];

    var textParts = [];
    var reasoningText = '';
    for (var i = 0; i < blocks.length; i++) {
      var blk = blocks[i];
      if (blk.type === 'reasoning') {
        var ta = document.querySelector('.edit-block-ta[data-block-idx="' + i + '"]');
        var text = ta ? ta.value.trim() : '';
        if (text) reasoningText = text;
      } else if (blk.type === 'text') {
        var ta = document.querySelector('.edit-block-ta[data-block-idx="' + i + '"]');
        var text = ta ? ta.value.trim() : '';
        if (text) textParts.push(text);
      } else if (blk.type === 'tool_boundary') {
        textParts.push('%%%TOOL_BOUNDARY%%%');
      }
    }

    var content = textParts.join('\n');
    var reasoning = reasoningText || null;

    try {
      await fetch(window.api.chatMessage(chatId, messageId), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: content,
          reasoning: reasoning,
          attachment_ids: window.currentEditAttachments.map(function (a) { return a.id; }),
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
    var chatId = document.getElementById('edit-msg-chat-id').value;
    if (!chatId) return;

    var formData = new FormData();
    files.forEach(function (f) { formData.append('files', f); });

    try {
      var res = await fetch(window.api.chatAttachments(chatId), {
        method: 'POST',
        body: formData,
      });
      if (res.ok) {
        var data = await res.json();
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
