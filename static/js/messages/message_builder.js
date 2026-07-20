(function () {
  /* ── SVG helpers ── */

  function _chevronSvg() {
    var html = (window.getSvgSprite('chevron-right', 12) || '').replace(
      '<svg', '<svg class="w-3 h-3 reasoning-chevron" style="color:var(--text-faint);transition:transform 0.2s ease"');
    var d = document.createElement('div');
    d.innerHTML = html;
    return d.firstElementChild;
  }

  function _summaryChevronSvg() {
    var html = (window.getSvgSprite('chevron-right', 12) || '').replace(
      '<svg', '<svg class="w-3 h-3 chevron"');
    var d = document.createElement('div');
    d.innerHTML = html;
    return d.firstElementChild;
  }

  /* ── Builder: assistant streaming skeleton ── */

  window.buildAssistantSkeleton = function (charName, charImagePath) {
    var div = document.createElement('div');
    div.className = 'message msg';
    div.id = 'streaming-message';

    var body = document.createElement('div');
    body.className = 'message-body';
    div.appendChild(body);

    var flex = document.createElement('div');
    flex.className = 'flex items-start gap-3 min-w-0';
    body.appendChild(flex);

    var avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    if (charImagePath) {
      var img = document.createElement('img');
      img.src = '/' + charImagePath;
      img.alt = '';
      img.className = 'cursor-pointer';
      img.addEventListener('click', function () { window.openLightbox(img.src); });
      avatar.appendChild(img);
    } else {
      avatar.textContent = window.escapeHtml((charName || 'A')[0]);
    }
    flex.appendChild(avatar);

    var col = document.createElement('div');
    col.className = 'min-w-0';
    flex.appendChild(col);

    var nameEl = document.createElement('div');
    nameEl.className = 'text-sm font-medium';
    nameEl.style.cssText = 'color:var(--text)';
    nameEl.textContent = window.escapeHtml(charName);
    col.appendChild(nameEl);

    var meta = document.createElement('div');
    meta.className = 'text-xs text-muted flex items-center gap-1.5 flex-wrap mt-0.5';
    col.appendChild(meta);

    var toggleBtn = document.createElement('button');
    toggleBtn.className = 'reasoning-toggle-btn hidden';
    toggleBtn.setAttribute('aria-label', 'Toggle reasoning');
    toggleBtn.addEventListener('click', function () { window.toggleReasoning(toggleBtn); });
    toggleBtn.appendChild(_chevronSvg());
    var toggleSpan = document.createElement('span');
    toggleSpan.textContent = 'Reasoning';
    toggleBtn.appendChild(toggleSpan);
    meta.appendChild(toggleBtn);

    var content = document.createElement('div');
    content.className = 'message-content markdown-content processed pl-stream';
    body.appendChild(content);

    var spinner = document.createElement('div');
    spinner.className = 'message-spinner';
    body.appendChild(spinner);

    return div;
  };

  /* ── Builder: user message div (temp) ── */

  window.buildUserMessageDiv = function (text, personaName, personaAvatar, stagedFiles) {
    var div = document.createElement('div');
    div.className = 'message relative msg';
    div.id = 'temp-user-msg';

    var body = document.createElement('div');
    body.className = 'message-body';
    div.appendChild(body);

    var flex = document.createElement('div');
    flex.className = 'flex items-start gap-3 min-w-0';
    body.appendChild(flex);

    var avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    if (personaAvatar) {
      var img = document.createElement('img');
      img.src = '/' + personaAvatar;
      img.alt = '';
      img.className = 'cursor-pointer';
      img.addEventListener('click', function () { window.openLightbox(img.src); });
      avatar.appendChild(img);
    } else {
      avatar.textContent = window.escapeHtml((personaName || 'Y')[0]);
    }
    flex.appendChild(avatar);

    var col = document.createElement('div');
    col.className = 'min-w-0';
    flex.appendChild(col);

    var nameEl = document.createElement('div');
    nameEl.className = 'text-sm font-medium';
    nameEl.style.cssText = 'color:var(--text)';
    nameEl.textContent = window.escapeHtml(personaName);
    col.appendChild(nameEl);

    if (stagedFiles && stagedFiles.length > 0) {
      var attContainer = document.createElement('div');
      attContainer.className = 'flex gap-2 flex-wrap mb-2 pl-stream';
      stagedFiles.forEach(function (f) { attContainer.appendChild(window.buildAttachmentPreview(f)); });
      body.insertBefore(attContainer, null);
    }

    var content = document.createElement('div');
    content.className = 'message-content markdown-content pl-stream';
    content.innerHTML = window.renderMessage(text);
    content.classList.add('processed');
    body.appendChild(content);

    return div;
  };

  /* ── Builder: attachment preview ── */

  window.buildAttachmentPreview = function (file) {
    var wrapper = document.createElement('div');
    wrapper.className = 'relative group';

    if (file.type.startsWith('image/')) {
      var img = document.createElement('img');
      img.className = 'h-24 rounded object-cover border border-border cursor-pointer hover:opacity-90 transition-opacity';
      img.src = URL.createObjectURL(file);
      img.alt = 'attachment';
      img.addEventListener('click', function () { window.openLightbox(img.src); });
      wrapper.appendChild(img);
    } else {
      wrapper.className = 'h-16 bg-surface-3 px-3 rounded border border-border flex items-center gap-2 text-sm';
      var iconSpan = document.createElement('span');
      iconSpan.innerHTML = window.getSvgSprite ? window.getSvgSprite('music', 18) : '';
      wrapper.appendChild(iconSpan);
      var audio = document.createElement('audio');
      audio.controls = true;
      audio.className = 'h-8 max-w-[200px]';
      audio.style.cssText = 'filter: contrast(0.8) grayscale(1)';
      var source = document.createElement('source');
      source.src = URL.createObjectURL(file);
      source.type = file.type;
      audio.appendChild(source);
      wrapper.appendChild(audio);
    }

    return wrapper;
  };

  /* ── Builder: tool call card ── */

  window.buildToolCallCard = function (call) {
    var details = document.createElement('details');
    details.className = 'details tool-call';
    details.setAttribute('data-call-id', call.id);

    var summary = document.createElement('summary');
    summary.appendChild(_summaryChevronSvg());

    var code = document.createElement('code');
    code.className = 'font-bold';
    code.textContent = window.escapeHtml(call.name);
    summary.appendChild(code);

    var argSpan = document.createElement('span');
    argSpan.className = 'truncate max-w-[300px]';
    argSpan.textContent = window.escapeHtml(JSON.stringify(call.arguments));
    summary.appendChild(argSpan);

    details.appendChild(summary);

    var resultBody = document.createElement('div');
    resultBody.className = 'tool-result-body';
    resultBody.style.display = 'none';

    var pre = document.createElement('pre');
    pre.className = 'whitespace-pre-wrap break-all';
    resultBody.appendChild(pre);
    details.appendChild(resultBody);

    return details;
  };

  /* ── Builder: reasoning block (indexed, used during streaming) ──
   *
   *  index === 0 → <div>  (no toggle — controlled by message-level button)
   *  index  > 0 → <details> (collapsible, matching server-side template)
   */

  window.buildReasoningBlock = function (index) {
    index = index || 0;
    if (index > 0) {
      var details = document.createElement('details');
      details.className = 'details reasoning-block pl-stream';
      details.setAttribute('data-think-id', String(index));
      var summary = document.createElement('summary');
      summary.appendChild(_summaryChevronSvg());
      summary.appendChild(document.createTextNode(' Reasoning'));
      details.appendChild(summary);
      var rc = document.createElement('div');
      rc.className = 'reasoning-content markdown-content';
      rc.style.whiteSpace = 'pre-wrap';
      details.appendChild(rc);
      return details;
    }
    var rb = document.createElement('div');
    rb.className = 'reasoning-block pl-stream';
    rb.setAttribute('data-think-id', '0');
    var rc = document.createElement('div');
    rc.className = 'reasoning-content markdown-content hidden';
    rc.style.whiteSpace = 'pre-wrap';
    rb.appendChild(rc);
    return rb;
  };

  /* ── Segment factories (single source of DOM structure per type) ── */

  window.segmentBuilders = {
    text: function () {
      var el = document.createElement('div');
      el.className = 'message-content markdown-content processed pl-stream';
      return el;
    },
    reasoning: function (index) {
      return window.buildReasoningBlock(index);
    },
    tool_calls: function (calls) {
      var el = document.createElement('div');
      el.className = 'tool-calls-stream pl-stream';
      for (var ci = 0; ci < calls.length; ci++) {
        el.appendChild(window.buildToolCallCard(calls[ci]));
      }
      return el;
    },
  };

  /* ── Tool card updater (moves DOM knowledge here, out of handlers) ── */

  window.updateToolCallCard = function (sectionEl, callId, result, isError) {
    var card = sectionEl.querySelector('[data-call-id="' + callId + '"]');
    if (!card) return;
    var label = card.querySelector('.executing-label');
    if (label) {
      label.textContent = isError ? '(error)' : '(done)';
      label.style.color = isError ? 'var(--danger)' : 'var(--accent)';
    }
    var body = card.querySelector('.tool-result-body');
    if (body) {
      body.style.display = 'block';
      var pre = body.querySelector('pre');
      if (pre) {
        pre.textContent = isError ? '(error) ' + result : result;
        pre.style.color = isError ? 'var(--danger)' : '';
      }
    }
  };
})();
