(function () {
  // A reasoning segment is stored as escaped text, and the server escapes only
  // `& < > "` (focus/core/message_render.py::escape_html). Decoding through the
  // parser reads that form and also an older variant saved with `&#39;`, so a
  // re-edit neither shows the entity nor re-escapes it into `&amp;#39;`.
  function decodeReasoningHtml(html) {
    var el = document.createElement('textarea');
    el.innerHTML = html || '';
    return el.value;
  }

  // Same character set as the server's escape_html — an apostrophe is text, not
  // an entity, so it must survive a save untouched.
  function escapeReasoningHtml(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function buildEditBlocks(content, segments, reasoning) {
    var blocks = [];
    if (segments && segments.length > 0) {
      for (var i = 0; i < segments.length; i++) {
        var seg = segments[i];
        if (seg.type === 'text') {
          if (seg.content && seg.content.trim()) {
            blocks.push({ type: 'text', content: seg.content });
          }
        } else if (seg.type === 'reasoning') {
          blocks.push({
            type: 'reasoning',
            content: decodeReasoningHtml(seg.html || ''),
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
    } else {
      if (reasoning) {
        blocks.push({ type: 'reasoning', content: reasoning.trim(), index: 0 });
      }
      if (content && content.trim()) {
        blocks.push({ type: 'text', content: content });
      }
    }

    var hasText = false;
    for (var i = 0; i < blocks.length; i++) {
      if (blocks[i].type === 'text') { hasText = true; break; }
    }
    if (!hasText) blocks.push({ type: 'text', content: '' });

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

  // The fields share the lane's height (flex, see modals.css) and scroll inside
  // themselves, so the editor holds one window size whatever the message is.

  // One editable segment is one block: a rail that names it and carries its
  // readout, then the textarea. The rail owns the verbs, so nothing floats over
  // the text and there is no native resize grip to fight the auto-height.
  function createBlock(name, idx, content, collapsible) {
    var section = document.createElement('section');
    section.className = 'msg-block' + (collapsible ? ' collapsed' : '');

    var rail = document.createElement('div');
    rail.className = 'rail';

    if (collapsible) {
      var toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'key sm';
      toggle.title = 'Show or hide ' + name.toLowerCase();
      toggle.setAttribute('aria-label', toggle.title);
      toggle.dataset.action = 'actionToggleEditBlock';
      toggle.innerHTML = '<span class="caret-mark"></span>';
      rail.appendChild(toggle);
    }

    var label = document.createElement('span');
    label.textContent = name;
    rail.appendChild(label);

    var count = document.createElement('span');
    count.className = 'row-value';
    count.dataset.ui = 'block-count';
    rail.appendChild(count);

    var actions = document.createElement('div');
    actions.className = 'rail-actions flush';
    var expand = document.createElement('button');
    expand.type = 'button';
    expand.className = 'key sm';
    expand.title = 'Expand editor';
    expand.setAttribute('aria-label', 'Expand editor');
    expand.dataset.action = 'actionOpenTextExpander';
    expand.dataset.targetId = 'edit-msg-ta-' + idx;
    expand.dataset.expanderTitle = 'Edit ' + name;
    expand.innerHTML = window.getSvgSprite('expand', 16);
    actions.appendChild(expand);
    rail.appendChild(actions);

    var ta = document.createElement('textarea');
    ta.className = 'field sized msg-block-text';
    ta.dataset.ui = 'edit-block-ta';
    ta.id = 'edit-msg-ta-' + idx;
    ta.setAttribute('data-block-idx', idx);
    ta.value = content || '';
    ta.addEventListener('input', function () {
      count.textContent = window.wordCountLabel(ta.value);
    });
    count.textContent = window.wordCountLabel(ta.value);

    section.appendChild(rail);
    section.appendChild(ta);
    return section;
  }

  // A collapsed block hides its textarea, not the rail: the name and the length
  // stay readable while the text is out of the way.
  window.actionToggleEditBlock = function (el) {
    var section = el.closest('.msg-block');
    if (!section) return;
    var collapsed = section.classList.toggle('collapsed');
    var caret = el.querySelector('.caret-mark');
    if (caret) caret.classList.toggle('caret-open', !collapsed);
  };

  function renderToolBlock(calls) {
    var section = document.createElement('section');
    section.className = 'msg-block msg-block-tool';
    var rail = document.createElement('div');
    rail.className = 'rail';
    rail.innerHTML = '<span>Tool calls</span>';
    section.appendChild(rail);
    if (!calls || !calls.length) {
      var sep = document.createElement('div');
      sep.className = 'divider';
      section.appendChild(sep);
      return section;
    }
    var body = window.buildToolCallsSection();
    for (var c = 0; c < calls.length; c++) {
      body.appendChild(renderToolCallCard(calls[c]));
    }
    section.appendChild(body);
    return section;
  }

  function renderEditBlocks(blocks) {
    var container = document.getElementById('edit-msg-blocks');
    if (!container) return;
    container.innerHTML = '';

    for (var i = 0; i < blocks.length; i++) {
      var blk = blocks[i];
      if (blk.type === 'reasoning') {
        container.appendChild(createBlock('Reasoning', i, blk.content, true));
      } else if (blk.type === 'text') {
        container.appendChild(createBlock('Text', i, blk.content, false));
      } else if (blk.type === 'tool_boundary') {
        container.appendChild(renderToolBlock(blk.calls));
      }
    }
  }

  window.editMessage = async function (messageId, chatId) {
    try {
      var res = await hxFetch(window.api.chatMessage(chatId, messageId));
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
    var empty = document.getElementById('edit-msg-att-empty');
    if (empty) empty.classList.toggle('hidden', window.currentEditAttachments.length > 0);
    if (window.currentEditAttachments.length === 0) return;

    window.currentEditAttachments.forEach(function (att, idx) {
      var thumbnail = window.createMediaThumbnail({
        src: att.file_path || '',
        mimeType: att.mime_type,
        size: 48,
        onClick: function () {
          var src = att.file_path || '';
          var external = /^(blob:|data:|https?:)/.test(src);
          window.openLightbox(external ? src : '/' + src);
        },
        onDelete: function () {
          window.deleteModalAttachment(idx);
        },
      });

      var wrapper = document.createElement('div');
      wrapper.className = 'relative shrink-0';

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
          segments.push({ type: 'reasoning', html: escapeReasoningHtml(text), index: blk.index || 0 });
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
      await hxJson(window.api.chatMessage(chatId, messageId), 'PATCH', {
        content: content,
        reasoning: reasoning,
        attachment_ids: window.currentEditAttachments.map(function (a) { return a.id; }),
        segments: segments,
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
      var res = await hxFetch(window.api.chatAttachments(chatId), {
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
    window.setupDropZone('#edit-msg-media', window.uploadMessageAttachmentFiles);
  }

  window._buildEditBlocks = buildEditBlocks;
})();
