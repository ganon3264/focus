(function () {
  window.createUserMessageDiv = function (text, stagedFiles, personaName, personaAvatarPath) {
    const userDiv = document.createElement('div');
    userDiv.className = 'message msg';

    const now = new Date();
    const dateStr = now.toISOString().slice(0, 10);
    const timeStr = now.toISOString().slice(11, 16);

    const messageList = document.getElementById('message-list');
    const msgIndex = messageList ? messageList.querySelectorAll('.message').length + 1 : 0;

    let attachPreview = '';
    if (stagedFiles && stagedFiles.length > 0) {
      attachPreview =
        '<div class="flex gap-2 flex-wrap mb-2">' +
        stagedFiles
          .map((f) => {
            if (f.type.startsWith('image/'))
              return `<img src="${URL.createObjectURL(f)}" class="h-24 rounded object-cover border border-border cursor-pointer" onclick="openLightbox(this.src)">`;
            return `<div class="h-16 bg-surface-3 px-2 rounded flex items-center text-xs">${window.getSvgSprite('music', 24)} ${f.name}</div>`;
          })
          .join('') +
        '</div>';
    }

    const avatarHtml = personaAvatarPath
      ? `<img src="/${personaAvatarPath}" alt="" class="cursor-pointer" onclick="openLightbox(this.src)">`
      : window.escapeHtml((personaName || 'U')[0]);

    userDiv.innerHTML = `
      <div class="message-body">
        <div class="flex items-start justify-between relative">
          <div class="flex items-start gap-3 min-w-0">
            <div class="message-avatar">${avatarHtml}</div>
            <div class="min-w-0">
              <div class="text-sm font-medium" style="color:var(--text)">${window.escapeHtml(personaName || 'You')}</div>
            </div>
          </div>
          <div class="relative shrink-0" style="margin-left:1rem">
            <div class="meta-right flex items-center gap-3 mt-0.5" style="transition:opacity 0.18s ease,transform 0.18s ease">
              <div class="text-xs text-right leading-tight shrink-0">
                <div class="text-muted">${dateStr}</div>
                <div style="color:var(--text-faint)">${timeStr}</div>
              </div>
              <div class="text-[1.75rem] font-bold leading-none select-none shrink-0" style="color:var(--text-faint)">#${msgIndex}</div>
            </div>
          </div>
        </div>
        ${attachPreview}
        <div class="message-content markdown-content processed" style="padding-left:3rem">${window.renderMessage(text)}</div>
      </div>
    `;
    return userDiv;
  };

  window.createAssistantPlaceholderDiv = function (charName, charImagePath) {
    const asstDiv = document.createElement('div');
    asstDiv.className = 'message msg';
    asstDiv.id = 'streaming-message';

    const avatarHtml = charImagePath
      ? `<img src="/${charImagePath}" alt="" class="cursor-pointer" onclick="openLightbox(this.src)">`
      : window.escapeHtml(charName[0] || 'A');

    asstDiv.innerHTML = `
      <div class="message-body">
        <div class="flex items-start justify-between relative">
          <div class="flex items-start gap-3 min-w-0">
            <div class="message-avatar">${avatarHtml}</div>
            <div class="min-w-0">
              <div class="text-sm font-medium" style="color:var(--text)">${window.escapeHtml(charName)}</div>
              <div class="text-xs text-muted flex items-center gap-1.5 flex-wrap mt-0.5">
                <button class="reasoning-toggle-btn hidden" onclick="toggleReasoning(this)" aria-label="Toggle reasoning" style="background:none;border:none;padding:0;font:inherit;cursor:pointer;display:inline-flex;align-items:center;gap:0.25rem">
                  <svg class="w-3 h-3 reasoning-chevron" style="color:var(--text-faint);transition:transform 0.2s ease" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                  <span>Reasoning</span>
                </button>
              </div>
            </div>
          </div>
        </div>
        <div class="message-content markdown-content processed" style="padding-left:3rem"></div>
      </div>
    `;
    return asstDiv;
  };
})();
