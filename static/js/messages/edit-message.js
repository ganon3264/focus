(function () {
  function unescapeHtml(s) {
    return (s || '')
      .replace(/&quot;/g, '"')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&amp;/g, '&');
  }

  function buildEditBlocks(content, segments, reasoning) {
    if (segments && segments.length > 0) {
      var blocks = [];
      for (var i = 0; i < segments.length; i++) {
        var seg = segments[i];
        if (seg.type === 'text') {
          if (seg.content && seg.content.trim()) {
            blocks.push({ type: 'text', content: seg.content });
          }
        } else if (seg.type === 'reasoning') {
          blocks.push({
            type: 'reasoning',
            content: unescapeHtml(seg.html || ''),
            index: seg.index || 0,
          });
        } else if (seg.type === 'tool_boundary') {
          if (seg.tool_calls && seg.tool_calls.length > 0) {
            blocks.push({ type: 'tool_boundary', calls: seg.tool_calls });
          } else {
            blocks.push({ type: 'tool_boundary', calls: null });
          }
        }
      }
      return blocks;
    }

    var blocks = [];
    if (reasoning) {
      blocks.push({ type: 'reasoning', content: reasoning.trim(), index: 0 });
    }
    if (content && content.trim()) {
      blocks.push({ type: 'text', content: content });
    }
    return blocks;
  }

  function renderToolCallCard(tc) {
    return window.buildToolCallCard({
      name: tc.function.name,
      arguments: tc.function.arguments,
      result: tc.result || '',
      image: tc.image_data || tc.image_url,
    });
  }

  function autoResizeTextarea(ta) {
    var lines = (ta.value || '').split('\n').length;
    ta.rows = Math.max(3, Math.min(lines, 20));
  }

  function createEditTextarea(idx, variant, content) {
    var ta = document.createElement('textarea');
    ta.className = 'field edit-block-ta edit-block-ta--' + variant;
    ta.dataset.ui = 'edit-block-ta';
    ta.id = 'edit-msg-ta-' + idx;
    ta.setAttribute('data-block-idx', idx);
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
        details.className = 'disclosure reasoning-block';
        details.dataset.ui = 'reasoning-block';
        details.innerHTML =
          '<summary>' +
          '<span class="caret-mark reasoning-chevron" aria-hidden="true"></span>' +
          '<span>Reasoning</span>' +
          '</summary>' +
          '<div style="margin-top:0.5rem"></div>';
        container.appendChild(details);
        var wrapper = details.querySelector('div');
        wrapper.appendChild(createEditTextarea(i, 'reasoning', blk.content));
      } else if (blk.type === 'text') {
        container.appendChild(createEditTextarea(i, 'text', blk.content));
      } else if (blk.type === 'tool_boundary') {
        if (blk.calls && blk.calls.length > 0) {
          var tcSection = window.buildToolCallsSection();
          for (var c = 0; c < blk.calls.length; c++) {
            tcSection.appendChild(renderToolCallCard(blk.calls[c]));
          }
          container.appendChild(tcSection);
        } else {
          var sep = document.createElement('div');
          sep.style.cssText = 'height:0;border-bottom:1px solid var(--hair);margin:0.25rem 0';
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

      var blocks = buildEditBlocks(data.content, data.segments, data.reasoning);
      window._editBlocks = blocks;

      document.getElementById('edit-msg-id').value = messageId;
      document.getElementById('edit-msg-chat-id').value = chatId;

      renderEditBlocks(blocks);

      window.currentEditAttachments = data.attachments || [];
      window.renderEditModalAttachments();

      window.openModal('modal-edit-message');
    } catch (err) {
      window.showErrorToast('Error editing message: ' + err.message);
    }
  };

  window.renderEditModalAttachments = function () {
    var container = document.getElementById('edit-msg-attachments');
    if (!container) return;

    container.innerHTML = '';
    if (window.currentEditAttachments.length === 0) {
      container.innerHTML =
        '<div class="edit-msg-drop-empty">No attachments</div>';
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
    var reasoningParts = [];
    var segments = [];
    for (var i = 0; i < blocks.length; i++) {
      var blk = blocks[i];
      if (blk.type === 'reasoning') {
        var ta = document.querySelector('[data-ui="edit-block-ta"][data-block-idx="' + i + '"]');
        var text = ta ? ta.value.trim() : '';
        if (text) {
          reasoningParts.push(text);
          segments.push({ type: 'reasoning', html: window.escapeHtml(text), index: blk.index || 0 });
        }
      } else if (blk.type === 'text') {
        var ta = document.querySelector('[data-ui="edit-block-ta"][data-block-idx="' + i + '"]');
        var text = ta ? ta.value.trim() : '';
        if (text) {
          textParts.push(text);
          segments.push({ type: 'text', content: text });
        }
      } else if (blk.type === 'tool_boundary') {
        if (blk.calls && blk.calls.length > 0) {
          segments.push({ type: 'tool_boundary', tool_calls: blk.calls });
        } else {
          segments.push({ type: 'tool_boundary' });
        }
      }
    }

    var content = textParts.join('\n');
    var reasoning = reasoningParts.length > 0 ? reasoningParts.join('\n') : null;

    try {
      await fetch(window.api.chatMessage(chatId, messageId), {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: content,
          reasoning: reasoning,
          attachment_ids: window.currentEditAttachments.map(function (a) { return a.id; }),
          segments: segments,
        }),
      });

      window.closeModal('modal-edit-message', { discard: true });

      if (typeof refreshSingleMessage === 'function') {
        refreshSingleMessage(chatId, messageId);
      } else if (window.refreshMessageList) {
        window.refreshMessageList(chatId, [messageId]);
      }
    } catch (err) {
      window.showErrorToast('Failed to save edit: ' + err.message);
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
        window.ModalController.setDirty('modal-edit-message', true);
      } else {
        window.showErrorToast('Failed to upload attachment');
      }
    } catch (err) {
      console.error(err);
    }
  };

  window.deleteModalAttachment = function (idx) {
    window.currentEditAttachments.splice(idx, 1);
    window.renderEditModalAttachments();
    window.ModalController.setDirty('modal-edit-message', true);
  };

  if (typeof window.setupDropZone === 'function') {
    window.setupDropZone('#edit-msg-attachments', window.uploadMessageAttachmentFiles);
  }

  window._buildEditBlocks = buildEditBlocks;
})();
