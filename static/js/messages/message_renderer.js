window.escapeHtml = function (text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
};

window.extractThoughtsSafely = function (text) {
  const codeBlocks = [];
  let processed = text.replace(/```[\s\S]*?(?:```|$)/g, (match) => {
    codeBlocks.push(match);
    return `%%%FOCUS_CODE_${codeBlocks.length - 1}%%%`;
  });

  processed = processed.replace(/`[^`\n]*`/g, (match) => {
    codeBlocks.push(match);
    return `%%%FOCUS_CODE_${codeBlocks.length - 1}%%%`;
  });

  processed = processed.replace(/<thought_signature>([\s\S]*?)(?:<\/thought_signature>|$)/g, '');

  const thoughts = [];
  processed = processed.replace(/<think>([\s\S]*?)(?:<\/think>|$)/g, function (match, p1) {
    const isClosed = match.includes('</think>');
    thoughts.push({ content: p1, isClosed: isClosed });
    return `\n\n%%%THINK_BLOCK_${thoughts.length - 1}%%%\n\n`;
  });

  for (let j = 0; j < codeBlocks.length; j++) {
    const marker = `%%%FOCUS_CODE_${j}%%%`;
    processed = processed.split(marker).join(codeBlocks[j]);
    for (let t of thoughts) {
      t.content = t.content.split(marker).join(codeBlocks[j]);
    }
  }

  return { thoughts, processed };
};

marked.use({ breaks: true });

window.renderMessage = function (text) {
  if (!text) return '';

  const extracted = window.extractThoughtsSafely(text);
  const thoughts = extracted.thoughts;
  let processed = extracted.processed;
  let html = DOMPurify.sanitize(marked.parse(processed));

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
    const safeInner = window.escapeHtml(t.content).trim().replace(/\n/g, '<br>');
    const chevron = window.getSvgSprite('chevron-right', 12) || '>';
    var detailsHtml;
    if (i === 0) {
      detailsHtml = `<div class="reasoning-block" data-think-id="${i}"><div class="reasoning-content hidden">${safeInner}</div></div>`;
    } else {
      detailsHtml = `<div class="reasoning-block" data-think-id="${i}"><button class="reasoning-summary" onclick="toggleReasoningBlock(this)" aria-expanded="false"><span class="reasoning-chevron">${chevron}</span> Reasoning</button><div class="reasoning-content hidden">${safeInner}</div></div>`;
    }

    const regex = new RegExp(`<p>%%%THINK_BLOCK_${i}%%%<\\/p>|%%%THINK_BLOCK_${i}%%%`, 'g');
    html = html.replace(regex, () => detailsHtml);
  }

  return html;
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
