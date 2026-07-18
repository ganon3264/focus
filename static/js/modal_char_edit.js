function openEditCharacterModal(btnElement) {
  document.getElementById('edit-char-id').value = btnElement.dataset.charId || '';
  const name = btnElement.dataset.charName || '';
  document.getElementById('edit-char-name').value = name;
  document.getElementById('edit-char-desc').value = btnElement.dataset.charDesc || '';

  const imgPath = btnElement.dataset.charImage;
  const preview = document.getElementById('edit-char-image-preview');
  const placeholder = document.getElementById('edit-char-image-placeholder');

  if (imgPath) {
    preview.src = '/' + imgPath + '?t=' + new Date().getTime();
    preview.style.display = 'block';
    placeholder.style.display = 'none';
  } else {
    preview.style.display = 'none';
    placeholder.innerText = name ? name.charAt(0).toUpperCase() : '?';
    placeholder.style.display = 'block';
  }

  const mediaSection = document.getElementById('edit-char-media-section');
  Array.from(mediaSection.children).forEach(el => {
      if (!el.classList.contains('block-media-btn') && !el.classList.contains('block-media-placeholder')) {
          el.remove();
      }
  });

  const placeholderText = mediaSection.querySelector('.block-media-placeholder');
  let mediaList = [];
  try {
      mediaList = JSON.parse(btnElement.dataset.charMedia || '[]');
  } catch (e) {
      console.error(e);
  }

  if (mediaList.length > 0 && placeholderText) {
      placeholderText.style.display = 'none';
  } else if (mediaList.length === 0 && placeholderText) {
      placeholderText.style.display = 'block';
  }

  mediaList.forEach(img => {
      const div = buildMediaThumbnail(img, (e) => deleteCharModalMedia(img.id), 'char-modal-media');
      mediaSection.insertBefore(div, mediaSection.lastElementChild.previousElementSibling);
  });

  document.getElementById('modal-edit-character').style.display = 'grid';
}

function uploadCharModalMedia(input) {
  if (!input.files || !input.files[0]) return;
  const id = document.getElementById('edit-char-id').value;
  const formData = new FormData();
  formData.append('file', input.files[0]);

  fetch('/api/characters/' + id + '/images', {
    method: 'POST',
    body: formData
  }).then(r => r.json()).then(data => {
    const mediaSection = document.getElementById('edit-char-media-section');
    if(!mediaSection) return;

    const div = buildMediaThumbnail(data, (e) => deleteCharModalMedia(data.id), 'char-modal-media');

    mediaSection.insertBefore(div, mediaSection.lastElementChild.previousElementSibling);

    const placeholder = mediaSection.querySelector('.block-media-placeholder');
    if (placeholder) placeholder.style.display = 'none';

    input.value = '';
    htmx.ajax('GET','/partials/characters-modal',{target:'#characters-modal-body',swap:'innerHTML'});
    if (window.CURRENT_CHAT_STATE && window.CURRENT_CHAT_STATE.character_id === id && window.reloadPromptArranger) {
      const presetId = window.CURRENT_CHAT_STATE.preset_id || (document.getElementById('prompt-arranger') && document.querySelector('#prompt-arranger .arranger-list') ? document.querySelector('#prompt-arranger .arranger-list').id.replace('arranger-list-', '') : null);
      if (presetId) reloadPromptArranger(presetId, 'prompt-arranger');
    }
  });
}

function deleteCharModalMedia(imageId) {
  const charId = document.getElementById('edit-char-id').value;
  fetch(`/api/characters/${charId}/images/${imageId}`, {
    method: 'DELETE'
  }).then(r => {
    if(r.ok) {
      const el = document.getElementById(`char-modal-media-${imageId}`);
      if(el) el.remove();
      htmx.ajax('GET','/partials/characters-modal',{target:'#characters-modal-body',swap:'innerHTML'});
      if (window.CURRENT_CHAT_STATE && window.CURRENT_CHAT_STATE.character_id === charId && window.reloadPromptArranger) {
        const presetId = window.CURRENT_CHAT_STATE.preset_id || (document.getElementById('prompt-arranger') && document.querySelector('#prompt-arranger .arranger-list') ? document.querySelector('#prompt-arranger .arranger-list').id.replace('arranger-list-', '') : null);
        if (presetId) reloadPromptArranger(presetId, 'prompt-arranger');
      }
    }
  });
}

function uploadCharacterAvatar(input) {
  if (!input.files || !input.files[0]) return;
  const id = document.getElementById('edit-char-id').value;

  openCropModal(input.files[0], (croppedBlob) => {
    const formData = new FormData();
    formData.append('file', croppedBlob, 'avatar.png');

    fetch('/api/characters/' + id + '/avatar', {
      method: 'POST',
      body: formData
    }).then(r => r.json()).then(data => {
      const preview = document.getElementById('edit-char-image-preview');
      const placeholder = document.getElementById('edit-char-image-placeholder');
      preview.src = '/' + data.avatar_path + '?t=' + new Date().getTime();
      preview.style.display = 'block';
      placeholder.style.display = 'none';

      htmx.ajax('GET','/partials/characters-modal',{target:'#characters-modal-body',swap:'innerHTML'});
    });
  });
  input.value = '';
}

function submitEditCharacter(e) {
  e.preventDefault();
  const id = document.getElementById('edit-char-id').value;
  const data = Object.fromEntries(new FormData(e.target));
  fetch('/api/characters/' + id, {
    method: 'PATCH',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  }).then(function(r){
    if(r.ok) {
      closeModal('modal-edit-character');
      htmx.ajax('GET','/partials/characters-modal',{target:'#characters-modal-body',swap:'innerHTML'});
    }
  });
}
