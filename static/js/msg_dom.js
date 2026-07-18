// DOM builders for chat message elements.
// Depends on window.escapeHtml, window.renderMessage, window.getSvgSprite

(function(){
  window.createUserMessageDiv = function(text, stagedFiles, personaInitial) {
    const userDiv = document.createElement('div');
    userDiv.className = 'message';

    let attachPreview = '';
    if (stagedFiles && stagedFiles.length > 0) {
      attachPreview = '<div class="flex gap-2 flex-wrap mb-2">' + stagedFiles.map(f => {
        if (f.type.startsWith('image/')) return `<img src="${URL.createObjectURL(f)}" class="h-24 rounded object-cover border border-border cursor-pointer" onclick="openLightbox(this.src)">`;
        return `<div class="h-16 bg-surface-3 px-2 rounded flex items-center text-xs">${window.getSvgSprite('music', 24)} ${f.name}</div>`;
      }).join('') + '</div>';
    }

    userDiv.innerHTML = `
      <div class="message-avatar">${window.escapeHtml(personaInitial || 'U')}</div>
      <div class="message-body">
        ${attachPreview}
        <div class="message-content markdown-content processed">${window.renderMessage(text)}</div>
      </div>
    `;
    return userDiv;
  };

  window.createAssistantPlaceholderDiv = function(charName, charImagePath) {
    const asstDiv = document.createElement('div');
    asstDiv.className = 'message';
    asstDiv.id = 'streaming-message';

    const avatarHtml = charImagePath
      ? `<img src="/${charImagePath}" alt="" class="cursor-pointer" onclick="openLightbox(this.src)">`
      : window.escapeHtml(charName[0] || 'A');

    asstDiv.innerHTML = `
      <div class="message-avatar">${avatarHtml}</div>
      <div class="message-body">
        <div class="message-header">${window.escapeHtml(charName)}</div>
        <div class="message-content markdown-content processed"></div>
      </div>
    `;
    return asstDiv;
  };
})();
