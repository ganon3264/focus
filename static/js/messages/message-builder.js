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

  window.buildMessageSpinner = function () {
    return tpl('tpl-message-spinner');
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
    var body = messageBody(div);
    body.appendChild(window.buildMessageContent());
    body.appendChild(window.buildMessageSpinner());
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

    card.querySelector('summary code').textContent = call.name;

    var args = card.querySelector('summary span');
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

    // The toggle lives in the first reasoning block's head, not on the rail:
    // reasoning reads inside the screen with the rest of the content.
    var block = msgEl.querySelector('[data-ui="reasoning-block"]:not(details)');
    if (!block) return null;

    var btn = tpl('tpl-reasoning-toggle');
    var head = block.querySelector('.disclosure-head');
    if (!head) {
      head = document.createElement('div');
      head.className = 'disclosure-head';
      block.insertBefore(head, block.firstChild);
    }
    head.appendChild(btn);
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
