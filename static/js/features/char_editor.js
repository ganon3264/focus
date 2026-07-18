function importCharPage(e) {
  e.preventDefault();
  document.getElementById('import-indicator').classList.remove('hidden');
  const formData = new FormData(e.target);
  fetch(window.api.charImport, {
    method: 'POST',
    body: formData,
  }).then(async (r) => {
    if (r.ok) {
      const data = await r.json();
      if (data.errors && data.errors.length) {
        alert(
          'Imported ' +
            data.imported.length +
            ' of ' +
            data.total +
            ' cards.\n\nErrors:\n' +
            data.errors
              .map(function (e) {
                return '• ' + e.filename + ': ' + e.error;
              })
              .join('\n'),
        );
      }
      window.location.reload();
    } else {
      r.text().then((t) => {
        alert('Import failed: ' + t);
        document.getElementById('import-indicator').classList.add('hidden');
      });
    }
  });
}

function promptDeleteChar(btn) {
  const charId = btn.dataset.charId;
  const charName = btn.dataset.charName;
  const html = `
    <div class="mb-4 text-sm" style="color:var(--text);">Delete character <strong>${charName}</strong>?</div>
    <div class="flex flex-col gap-3">
      <label class="flex items-start gap-3 cursor-pointer p-3 rounded-lg hover:bg-(--surface-3) transition-colors border border-(--border) relative group">
        <div class="mt-0.5">
          <input type="radio" name="char_delete_option" value="soft" checked class="w-4 h-4 cursor-pointer" style="accent-color: var(--accent);">
        </div>
        <div class="flex flex-col">
          <span class="text-sm font-bold" style="color:var(--text);">Move Character to Trash</span>
          <span class="text-xs text-muted">You can restore the character later.</span>
        </div>
      </label>
      <label class="flex items-start gap-3 cursor-pointer p-3 rounded-lg hover:bg-(--surface-3) transition-colors border border-(--border) relative group">
        <div class="mt-0.5">
          <input type="radio" name="char_delete_option" value="soft_with_chats" class="w-4 h-4 cursor-pointer" style="accent-color: var(--accent);">
        </div>
        <div class="flex flex-col">
          <span class="text-sm font-bold" style="color:var(--text);">Move Character & Conversations to Trash</span>
          <span class="text-xs text-muted">Hides their chats too. Both can be restored.</span>
        </div>
      </label>
    </div>
  `;
  window.customConfirm(html, function () {
    const selected = document.querySelector('input[name="char_delete_option"]:checked').value;
    const delChats = selected === 'soft_with_chats';
    fetch(window.api.charDelete(charId, delChats), {
      method: 'DELETE',
    }).then((r) => {
      if (r.ok) window.location.href = '/characters';
    });
  });
}

document.addEventListener('alpine:init', () => {
  Alpine.data('charEditor', () => ({
    detailId: null,
    charsList: window.ALL_CHARS || [],

    get activeChar() {
      if (!this.detailId) return null;
      return this.charsList.find((c) => c.id === this.detailId);
    },

    selectChar(id) {
      this.detailId = id;
    },

    init() {
      const urlParams = new URLSearchParams(window.location.search);
      const charParam = urlParams.get('char');
      if (charParam && this.charsList.find((c) => c.id === charParam)) {
        this.detailId = charParam;
      } else if (this.charsList.length > 0) {
        this.detailId = this.charsList[0].id;
      }
    },
  }));
});

function uploadAdvancedAvatar(input) {
  const charId = input.dataset.charId;
  handleAvatarUpload(input, window.api.charAvatar(charId), (data) => {
    window.location.href = window.location.pathname + '?char=' + charId;
  });
}

function saveCharCard(btn) {
  const charId = btn.dataset.charId;
  const greetingsContainer = document.getElementById('greetings-list-' + charId);
  const textareas = greetingsContainer.querySelectorAll('textarea');
  const alternateGreetings = Array.from(textareas)
    .map((ta) => ta.value)
    .filter((val) => val.trim() !== '');

  const payload = {
    name: document.getElementById('char-name-' + charId).value,
    description: document.getElementById('char-desc-' + charId).value,
    personality: document.getElementById('char-personality-' + charId).value,
    scenario: document.getElementById('char-scenario-' + charId).value,
    first_mes: document.getElementById('char-first-' + charId).value,
    mes_example: document.getElementById('char-example-' + charId).value,
    alternate_greetings: alternateGreetings,
  };

  fetch(window.api.characters(charId), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }).then(function (r) {
    if (r.ok) {
      const originalText = btn.innerText;
      btn.innerText = 'Saved!';
      btn.classList.add('bg-green-600', 'border-green-600');
      setTimeout(() => {
        btn.innerText = originalText;
        btn.classList.remove('bg-green-600', 'border-green-600');
      }, 1500);
    }
  });
}

function addGreeting(charId) {
  const template = document.getElementById('greeting-template');
  const container = document.getElementById(`greetings-list-${charId}`);
  const clone = template.content.cloneNode(true);
  container.insertBefore(clone, container.firstChild);
}

function updateBlock(el, data) {
  const charId = el.dataset.charId;
  const blockId = el.dataset.blockId;
  fetch(window.api.charBlock(charId, blockId), {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

function deleteBlock(btn) {
  const charId = btn.dataset.charId;
  const blockId = btn.dataset.blockId;
  fetch(window.api.charBlock(charId, blockId), {
    method: 'DELETE',
  }).then((r) => {
    if (r.ok) {
      document.getElementById(`block-${blockId}`).remove();
    }
  });
}

function addBlock(charId) {
  fetch(window.api.charBlocks(charId), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: 'New Block', content: '', role: 'system' }),
  })
    .then((r) => r.json())
    .then((data) => {
      const blockId = data.id;
      const template = document.getElementById('block-template');
      const container = document.getElementById(`blocks-container-${charId}`);

      const emptyMsg = document.getElementById(`empty-blocks-msg-${charId}`);
      if (emptyMsg) emptyMsg.style.display = 'none';

      const clone = template.content.cloneNode(true);
      const wrapper = clone.querySelector('.block-item');
      wrapper.id = `block-${blockId}`;

      const nameInput = wrapper.querySelector('.block-name');
      nameInput.dataset.charId = charId;
      nameInput.dataset.blockId = blockId;
      nameInput.onchange = (e) => updateBlock(e.target, { name: e.target.value });

      const roleSelect = wrapper.querySelector('.block-role');
      roleSelect.dataset.charId = charId;
      roleSelect.dataset.blockId = blockId;
      roleSelect.onchange = (e) => updateBlock(e.target, { role: e.target.value });

      const contentTextarea = wrapper.querySelector('.block-content');
      contentTextarea.dataset.charId = charId;
      contentTextarea.dataset.blockId = blockId;
      contentTextarea.onchange = (e) => updateBlock(e.target, { content: e.target.value });

      const deleteBtn = wrapper.querySelector('.block-delete');
      deleteBtn.dataset.charId = charId;
      deleteBtn.dataset.blockId = blockId;
      deleteBtn.onclick = () => deleteBlock(deleteBtn);

      const mediaSection = wrapper.querySelector('.char-block-media-section');
      mediaSection.id = `media-section-${blockId}`;
      const mediaInput = wrapper.querySelector('.block-media-input');
      mediaInput.dataset.charId = charId;
      mediaInput.dataset.blockId = blockId;
      mediaInput.onchange = (e) => uploadCharBlockMedia(e.target);

      container.insertBefore(clone, container.firstChild);
    });
}

function uploadCharMedia(input) {
  const charId = input.dataset.charId;
  if (!input.files || !input.files[0]) return;
  const formData = new FormData();
  formData.append('file', input.files[0]);
  fetch(window.api.charImages(charId), {
    method: 'POST',
    body: formData,
  })
    .then((r) => r.json())
    .then((data) => {
      const mediaSection = document.getElementById(`media-section-char-${charId}`);
      if (!mediaSection) return;

      const div = window.buildMediaThumbnail(data, (e) => deleteCharMedia(charId, data.id), 'char-media');

      mediaSection.insertBefore(div, mediaSection.lastElementChild.previousElementSibling);

      const placeholder = mediaSection.querySelector('.block-media-placeholder');
      if (placeholder) placeholder.remove();

      input.value = '';
    });
}

function deleteCharMedia(el) {
  const container = el.closest ? el.closest('[data-media-id]') : el;
  const imageId = container ? container.dataset.mediaId : '';
  const mediaSection = container ? container.closest('.char-block-media-section') : null;
  const charId = mediaSection ? mediaSection.id.replace('media-section-char-', '') : '';
  fetch(window.api.charImage(charId, imageId), {
    method: 'DELETE',
  }).then((r) => {
    if (r.ok) {
      if (container) container.remove();
    }
  });
}

function uploadCharBlockMedia(input) {
  const charId = input.dataset.charId;
  const blockId = input.dataset.blockId;
  if (!input.files || !input.files[0]) return;
  const formData = new FormData();
  formData.append('file', input.files[0]);
  fetch(window.api.charBlockImages(charId, blockId), {
    method: 'POST',
    body: formData,
  })
    .then((r) => r.json())
    .then((data) => {
      const mediaSection = document.getElementById(`media-section-${blockId}`);
      if (!mediaSection) return;

      const div = window.buildMediaThumbnail(
        data,
        (e) => deleteCharBlockMedia(charId, blockId, data.id),
        'media',
      );

      mediaSection.insertBefore(div, mediaSection.lastElementChild);

      const placeholder = mediaSection.querySelector('.block-media-placeholder');
      if (placeholder) placeholder.remove();

      input.value = '';
    });
}

function deleteCharBlockMedia(el) {
  const container = el.closest ? el.closest('[data-media-id]') : el;
  const imageId = container ? container.dataset.mediaId : '';
  const blockItem = container ? container.closest('.block-item') : null;
  const blockId = blockItem ? blockItem.id.replace('block-', '') : '';
  const charId = container ? container.closest('[data-char-id]')?.dataset.charId || '' : '';
  fetch(window.api.charBlockImage(charId, blockId, imageId), {
    method: 'DELETE',
  }).then((r) => {
    if (r.ok) {
      if (container) container.remove();
    }
  });
}
