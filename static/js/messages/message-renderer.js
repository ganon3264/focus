window.escapeHtml = function (text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
};

window.extractThoughtsSafely = function (text) {
  text = (text || '').replace(/<thought_signature>[\s\S]*?(?:<\/thought_signature>|$)/g, '');
  return { thoughts: [], processed: text };
};

window.closeMarkdown = function (text) {
  if (!text) return text;
  var stack = [];
  var inFence = false;
  var inCode = false;
  var i = 0;
  while (i < text.length) {
    var ch = text[i];
    if (ch === '\\' && i + 1 < text.length) {
      i += 2;
      continue;
    }
    if (text.slice(i, i + 3) === '```') {
      if (inFence) {
        inFence = false;
        stack.pop();
      } else {
        inFence = true;
        stack.push('fence');
      }
      i += 3;
      continue;
    }
    if (inFence) {
      i++;
      continue;
    }
    if (inCode) {
      if (ch === '`') {
        inCode = false;
        stack.pop();
      }
      i++;
      continue;
    }
    if (ch === '`') {
      inCode = true;
      stack.push('code');
      i++;
      continue;
    }
    if (text.slice(i, i + 2) === '**') {
      var top = stack[stack.length - 1];
      if (top === 'bold') {
        stack.pop();
      } else {
        stack.push('bold');
      }
      i += 2;
      continue;
    }
    if (ch === '*' && text[i + 1] !== '*') {
      var top = stack[stack.length - 1];
      if (top === 'italic') {
        stack.pop();
      } else {
        stack.push('italic');
      }
      i++;
      continue;
    }
    i++;
  }
  if (stack.length === 0) return text;
  var suffix = '';
  for (var j = stack.length - 1; j >= 0; j--) {
    switch (stack[j]) {
      case 'fence': suffix += '\n```'; break;
      case 'code': suffix += '`'; break;
      case 'bold': suffix += '**'; break;
      case 'italic': suffix += '*'; break;
    }
  }
  return text + suffix;
};

marked.use({ breaks: true });

window.renderMessage = function (text, startThinkIdx, reasoning) {
  if (!text && !reasoning) return '';
  startThinkIdx = startThinkIdx || 0;

  text = window.closeMarkdown(text || '');
  const extracted = window.extractThoughtsSafely(text);
  let processed = extracted.processed;

  const thoughts = [];
  if (reasoning) {
    thoughts.push({ content: reasoning });
  }

  let html = DOMPurify.sanitize(marked.parse(processed));

  // Replace externally-sourced <img> tags with click-to-load placeholders.
  // Matches src="http://...", src="https://...", src="//...".
  // data: and embeded:// URIs are left alone.
  html = html.replace(
    /<img\s[^>]*?src\s*=\s*"((?:https?:)?\/\/[^"]*)"([^>]*?)(\/?\s*>)/gi,
    function (match, src, rest, closing) {
      var alt = (match.match(/alt\s*=\s*"([^"]*)"/i) || [])[1] || '';
      return '<span class="external-media-placeholder" data-src="' + src.replace(/"/g, '&quot;') + '" data-alt="' + alt.replace(/"/g, '&quot;') + '"><span class="external-media-label">External media</span><button class="external-media-btn" data-action="loadExternalMedia">Load</button></span>';
    }
  );

  const codeStash = [];
  html = html.replace(/<(code|pre)\b[^>]*>[\s\S]*?<\/\1>/g, (m) => {
    codeStash.push(m);
    return `%%%ACCENT_CODE_${codeStash.length - 1}%%%`;
  });

  {
    let result = '';
    const tagStack = [];
    for (let pos = 0; pos < html.length; pos++) {
      const ch = html[pos];
      if (ch === '<') {
        const tagEnd = html.indexOf('>', pos);
        if (tagEnd === -1) {
          result += ch;
          continue;
        }
        const tag = html.slice(pos, tagEnd + 1);

        if (tag.startsWith('</')) {
          const tagName = tag.match(/<\/(\w+)/)?.[1];
          if (tagName) {
            for (let j = tagStack.length - 1; j >= 0; j--) {
              if (tagStack[j].name === tagName) {
                tagStack.splice(j);
                break;
              }
            }
          }
        } else if (
          !tag.endsWith('/>') &&
          !tag.match(/<(area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)\b/i)
        ) {
          const tagName = tag.match(/<(\w+)/)?.[1];
          if (tagName) {
            tagStack.push({ name: tagName, styled: /style\s*=/i.test(tag) });
          }
        }

        result += tag;
        pos = tagEnd;
      } else if (ch === '"' && !tagStack.some((t) => t.styled)) {
        let end = pos + 1;
        while (end < html.length && html[end] !== '"') {
          if (html[end] === '<') {
            const tagEnd = html.indexOf('>', end);
            if (tagEnd === -1) break;
            end = tagEnd;
          }
          end++;
        }
        if (end < html.length && html[end] === '"') {
          result += '<span class="accent-quote">"' + html.slice(pos + 1, end) + '"</span>';
          pos = end;
        } else {
          result += ch;
        }
      } else {
        result += ch;
      }
    }
    html = result;
  }
  html = html.replace(/%%%ACCENT_CODE_(\d+)%%%/g, (_, i) => {
    const stashed = codeStash[+i];
    if (stashed.startsWith('<pre')) {
      return stashed.replace(
        '</pre>',
        `<button class="copy-btn" title="Copy code">${window.getSvgSprite('copy', 14)}</button></pre>`,
      );
    }
    return stashed;
  });

  for (let i = 0; i < thoughts.length; i++) {
    const t = thoughts[i];
    const completedContent = window.closeMarkdown(t.content);
    let safeInner = DOMPurify.sanitize(marked.parse(completedContent, { breaks: true }));
    const chevron = (window.getSvgSprite('chevron-right', 12) || '>').replace('<svg', '<svg class="chevron"');
    var globalIdx = startThinkIdx + i;
    if (globalIdx === 0) {
      html = `<div class="reasoning-block" data-think-id="0"><div class="reasoning-content markdown-content hidden">${safeInner}</div></div>` + html;
    } else {
      html += `<details class="details reasoning-block" data-think-id="${globalIdx}"><summary>${chevron} Reasoning</summary><div class="reasoning-content markdown-content">${safeInner}</div></details>`;
    }
  }

  return html;
};

window.loadExternalMedia = function (el) {
  var placeholder = el.closest('.external-media-placeholder');
  if (!placeholder) return;
  var img = document.createElement('img');
  img.src = placeholder.dataset.src;
  if (placeholder.dataset.alt) img.alt = placeholder.dataset.alt;
  img.loading = 'lazy';
  placeholder.replaceWith(img);
};

document.addEventListener('click', function (e) {
  const btn = e.target.closest('.copy-btn');
  if (!btn) return;
  const pre = btn.closest('pre');
  const code = pre && pre.querySelector('code');
  if (!code) return;
  navigator.clipboard.writeText(code.textContent);
  btn.innerHTML = window.getSvgSprite('check', 14);
  btn.classList.add('copied');
  setTimeout(() => {
    btn.innerHTML = window.getSvgSprite('copy', 14);
    btn.classList.remove('copied');
  }, 2000);
});
