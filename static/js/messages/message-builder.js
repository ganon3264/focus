// Client-side message chrome. Markup lives in templates/macros.html and is
// rendered once per page into the inert <template> blocks of
// partials/chat/message-templates.html; this module only clones and fills.
(function () {
  function tpl(id) {
    var node = document.getElementById(id);
    if (!node || !node.content) return null;
    var root = node.content.firstElementChild;
    return root ? root.cloneNode(true) : null;
  }

  function fillHeader(root, name, imagePath, initial) {
    var avatar = root.querySelector('[data-slot="avatar"]');
    if (avatar) {
      avatar.removeAttribute('data-slot');
      var img = avatar.querySelector('img');
      if (img && imagePath) {
        img.removeAttribute('data-slot');
        img.src = '/' + imagePath;
        img.alt = name + ' avatar';
      } else if (img) {
        avatar.insertBefore(document.createTextNode(initial), img);
        img.remove();
      }
    }
    var author = root.querySelector('[data-slot="author"]');
    if (author) {
      author.removeAttribute('data-slot');
      author.textContent = name;
    }
  }

  function messageBody(root) {
    return root.querySelector('[data-ui="message-body"]');
  }

  window.buildMessageContent = function () {
    return tpl('tpl-message-content');
  };

  window.buildMessagePending = function () {
    return tpl('tpl-message-pending');
  };

  window.showMessagePending = function (asstDiv) {
    var lines = asstDiv && asstDiv.querySelector('.message-header-lines');
    if (!lines || lines.querySelector('[data-ui="message-pending"]')) return;
    var pending = window.buildMessagePending();
    if (pending) lines.appendChild(pending);
  };

  window.hideMessagePending = function (asstDiv) {
    if (!asstDiv) return;
    var pending = asstDiv.querySelectorAll('[data-ui="message-pending"]');
    for (var i = 0; i < pending.length; i++) pending[i].remove();
    asstDiv.classList.remove('is-waiting', 'is-reasoning', 'is-content');
  };

  // The phase tempo is declared in CSS as --tick-rate; it has to be applied
  // here, because a duration change in CSS would restart the animation from the
  // first cell instead of continuing where the previous phase left it. Applied
  // only when the phase (or the ticker node) changes — a token must not force a
  // style flush.
  var tickPhase = new WeakMap();

  function applyTickRate(host) {
    if (!host.querySelectorAll || !window.getComputedStyle) return;
    var rate = parseFloat(window.getComputedStyle(host).getPropertyValue('--tick-rate'));
    if (!rate) rate = 1;
    var cells = host.querySelectorAll('.spinner.scan > i');
    for (var i = 0; i < cells.length; i++) {
      if (!cells[i].getAnimations) continue;
      var anims = cells[i].getAnimations();
      for (var j = 0; j < anims.length; j++) anims[j].playbackRate = rate;
    }
  }

  // "Has a child" and "has output" are two different questions. A segment that
  // has arrived proves the model answered, even while its reasoning is folded
  // (the screen stays out of the layout, but the phase is no longer waiting).
  // The ticker stays up for the whole run; the phase changes its hue and rate.
  window.syncStreamingView = function (asstDiv) {
    if (!asstDiv) return;
    // Only a node that is on the wire carries a phase class. A finished message
    // calling in (opening its reasoning) must not sprout a ticker.
    if (
      !asstDiv.classList.contains('is-waiting') &&
      !asstDiv.classList.contains('is-reasoning') &&
      !asstDiv.classList.contains('is-content')
    ) return;
    var body = asstDiv.querySelector('[data-ui="message-body"]');
    if (!body) return;
    var visible = false;
    var hasOutput = false;
    var kids = body.children;
    for (var i = 0; i < kids.length; i++) {
      var el = kids[i];
      if (el.matches('[data-ui~="message-content"]')) {
        hasOutput = true;
        if (el.textContent.trim()) visible = true;
        continue;
      }
      if (el.matches('[data-ui="reasoning-block"]')) {
        var content = el.querySelector('[data-ui~="reasoning-content"]');
        if (content && !content.classList.contains('hidden') && (el.tagName !== 'DETAILS' || el.open)) {
          visible = true;
        }
        continue;
      }
      hasOutput = true;
      visible = true;
    }
    var phase = kids.length === 0 ? 'is-waiting' : (hasOutput ? 'is-content' : 'is-reasoning');
    var hadTicker = !!asstDiv.querySelector('[data-ui="message-pending"]');
    body.classList.toggle('is-empty', !visible);
    asstDiv.classList.toggle('is-waiting', phase === 'is-waiting');
    asstDiv.classList.toggle('is-reasoning', phase === 'is-reasoning');
    asstDiv.classList.toggle('is-content', phase === 'is-content');
    window.showMessagePending(asstDiv);
    if (!hadTicker || tickPhase.get(asstDiv) !== phase) {
      tickPhase.set(asstDiv, phase);
      applyTickRate(asstDiv);
    }
  };

  window.buildToolCallsSection = function () {
    return tpl('tpl-tool-calls-section');
  };

  window.buildMessageShell = function (role) {
    var div = tpl(role === 'user' ? 'tpl-message-shell-user' : 'tpl-message-shell-assistant');
    if (!div) return null;
    div.id = role === 'user' ? 'temp-user-msg' : 'streaming-message';
    return div;
  };

  window.buildAssistantSkeleton = function (charName, charImagePath) {
    var div = window.buildMessageShell('assistant');
    if (!div) return null;
    fillHeader(div, charName, charImagePath, (charName || 'A')[0]);
    div.classList.add('is-waiting');
    var body = messageBody(div);
    if (body) body.classList.add('is-empty');
    window.showMessagePending(div);
    return div;
  };

  window.buildAttachmentPreview = function (file) {
    var isImage = (file.type || '').indexOf('image/') === 0;
    var wrapper = tpl(isImage ? 'tpl-attachment-image' : 'tpl-attachment-audio');
    if (!wrapper) return null;
    var url = URL.createObjectURL(file);
    if (isImage) {
      wrapper.querySelector('img').src = url;
    } else {
      var source = wrapper.querySelector('source');
      source.src = url;
      source.type = file.type;
    }
    return wrapper;
  };

  window.buildUserMessageDiv = function (text, personaName, personaAvatar, stagedFiles) {
    var div = window.buildMessageShell('user');
    if (!div) return null;
    fillHeader(div, personaName, personaAvatar, (personaName || 'Y')[0]);

    var body = messageBody(div);
    if (stagedFiles && stagedFiles.length > 0) {
      var row = tpl('tpl-attachment-row');
      stagedFiles.forEach(function (f) { row.appendChild(window.buildAttachmentPreview(f)); });
      body.appendChild(row);
    }

    var content = window.buildMessageContent();
    content.innerHTML = window.renderMessage(text);
    body.appendChild(content);
    return div;
  };

  // One tool-call card for every path: streaming (call_id + result later),
  // edit modal (read-only, result + image already known) and the server render
  // (same macro). Fillable nodes are addressed by the hooks the markup already
  // carries — no class selectors, no extra attributes.
  window.buildToolCallCard = function (call) {
    var card = tpl('tpl-tool-call');
    if (!card) return null;

    var nameEl = card.querySelector('[data-ui="tool-name"]');
    if (nameEl) nameEl.textContent = call.name;

    // The args node is its own hook: a plain `summary span` also matches the
    // drawn caret, which then swallows the JSON and rotates it 45°.
    var args = card.querySelector('[data-ui="tool-args"]');
    var argStr = typeof call.arguments === 'string' ? call.arguments : JSON.stringify(call.arguments || {});
    if (args) {
      if (argStr && argStr !== '{}') args.textContent = argStr;
      else args.remove();
    }

    if (call.callId) card.setAttribute('data-call-id', call.callId);

    var body = card.querySelector('[data-ui="tool-result-body"]');
    var img = body.querySelector('img');
    if (img) {
      if (call.image) {
        img.src = call.image;
      } else {
        // An <img> with no src renders nothing and requests nothing; it stays
        // in the card so a late image_url has a node to land on.
        img.removeAttribute('src');
        img.style.display = 'none';
      }
    }

    if (call.result == null) {
      body.style.display = 'none';
    } else {
      body.querySelector('pre').textContent = call.result;
    }

    return card;
  };

  // Reasoning block used during streaming
  //   index === 0 → <div>  (no toggle — controlled by message-level button)
  //   index  > 0 → <details> (collapsible, matching server-side template)
  function buildReasoningBlock(index) {
    index = index || 0;
    var el = tpl(index > 0 ? 'tpl-reasoning-block' : 'tpl-reasoning-first');
    if (!el) return null;
    if (index > 0) el.setAttribute('data-think-id', String(index));
    var content = el.querySelector('[data-ui~="reasoning-content"]');
    if (content) content.style.whiteSpace = 'pre-wrap';
    return el;
  }

  // Ensure the message-level reasoning toggle button exists in the meta row,
  // creating it if the reused server HTML omitted it (e.g. regenerating from a
  // variant that had no reasoning). A separator dot is added only when the meta
  // row already has content (the model name), matching the server template.
  window.ensureReasoningToggleButton = function (msgEl) {
    var existing = msgEl.querySelector('[data-ui="reasoning-toggle-btn"]');
    if (existing) return existing;

    var btn = tpl('tpl-reasoning-toggle');
    var meta = msgEl.querySelector('[data-ui="message-meta"]');
    if (meta) {
      if (meta.children.length > 0) {
        var dot = document.createElement('span');
        dot.className = 'meta-sep';
        dot.setAttribute('aria-hidden', 'true');
        meta.appendChild(dot);
      }
      meta.appendChild(btn);
    } else {
      msgEl.appendChild(btn);
    }
    return btn;
  };

  // Segment factories — single source of DOM structure per type
  window.segmentBuilders = {
    text: function () {
      return window.buildMessageContent();
    },
    reasoning: function (index) {
      return buildReasoningBlock(index);
    },
    tool_calls: function (calls) {
      var el = tpl('tpl-tool-calls-stream');
      for (var ci = 0; ci < calls.length; ci++) {
        el.appendChild(window.buildToolCallCard({
          name: calls[ci].name,
          arguments: calls[ci].arguments,
          callId: calls[ci].id,
        }));
      }
      return el;
    },
  };

  window.updateToolCallCard = function (sectionEl, callId, result, isError, imageUrl) {
    var card = sectionEl.querySelector('[data-call-id="' + callId + '"]');
    if (!card) return;
    var label = card.querySelector('[data-ui="executing-label"]');
    if (label) {
      label.textContent = isError ? '(error)' : '(done)';
      label.style.color = isError ? 'var(--danger)' : 'var(--accent)';
    }
    var body = card.querySelector('[data-ui="tool-result-body"]');
    if (body) {
      body.style.display = 'block';
      var pre = body.querySelector('pre');
      if (pre) {
        pre.textContent = isError ? '(error) ' + result : result;
        pre.style.color = isError ? 'var(--danger)' : '';
      }
      if (imageUrl) {
        var img = body.querySelector('img');
        if (img) {
          img.src = imageUrl;
          img.style.display = '';
        }
      }
    }
  };
})();
