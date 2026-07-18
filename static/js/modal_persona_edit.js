function openEditPersonaModal(btnElement) {
  document.getElementById('edit-persona-id').value = btnElement.dataset.personaId || '';
  const name = btnElement.dataset.personaName || '';
  document.getElementById('edit-persona-name').value = name;
  document.getElementById('edit-persona-desc').value = btnElement.dataset.personaDesc || '';

  const imgPath = btnElement.dataset.personaImage;
  const preview = document.getElementById('edit-persona-image-preview');
  const placeholder = document.getElementById('edit-persona-image-placeholder');

  if (imgPath) {
    preview.src = '/' + imgPath + '?t=' + new Date().getTime();
    preview.style.display = 'block';
    placeholder.style.display = 'none';
  } else {
    preview.style.display = 'none';
    placeholder.innerText = name ? name.charAt(0).toUpperCase() : '?';
    placeholder.style.display = 'block';
  }

  const mediaSection = document.getElementById('edit-persona-media-section');
  Array.from(mediaSection.children).forEach(el => {
      if (!el.classList.contains('block-media-btn') && !el.classList.contains('block-media-placeholder')) {
          el.remove();
      }
  });

  const placeholderText = mediaSection.querySelector('.block-media-placeholder');
  let mediaList = [];
  try {
      mediaList = JSON.parse(btnElement.dataset.personaMedia || '[]');
  } catch (e) {
      console.error(e);
  }

  if (mediaList.length > 0 && placeholderText) {
      placeholderText.style.display = 'none';
  } else if (mediaList.length === 0 && placeholderText) {
      placeholderText.style.display = 'block';
  }

  mediaList.forEach(img => {
      const div = buildMediaThumbnail(img, (e) => deletePersonaMedia(img.id), 'persona-media');
      mediaSection.insertBefore(div, mediaSection.lastElementChild.previousElementSibling);
  });

  document.getElementById('modal-edit-persona').style.display = 'grid';
}

function uploadPersonaMedia(input) {
  if (!input.files || !input.files[0]) return;
  const id = document.getElementById('edit-persona-id').value;
  const formData = new FormData();
  formData.append('file', input.files[0]);

  fetch('/api/personas/' + id + '/images', {
    method: 'POST',
    body: formData
  }).then(r => r.json()).then(data => {
    const mediaSection = document.getElementById('edit-persona-media-section');
    if(!mediaSection) return;

    const div = buildMediaThumbnail(data, (e) => deletePersonaMedia(data.id), 'persona-media');

    mediaSection.insertBefore(div, mediaSection.lastElementChild.previousElementSibling);

    const placeholder = mediaSection.querySelector('.block-media-placeholder');
    if (placeholder) placeholder.style.display = 'none';

    input.value = '';
    htmx.ajax('GET','/partials/personas-modal',{target:'#personas-modal-body',swap:'innerHTML'});
    if (window.CURRENT_CHAT_STATE && window.CURRENT_CHAT_STATE.persona_id === id && window.reloadPromptArranger) {
      const presetId = window.CURRENT_CHAT_STATE.preset_id || (document.getElementById('prompt-arranger') && document.querySelector('#prompt-arranger .arranger-list') ? document.querySelector('#prompt-arranger .arranger-list').id.replace('arranger-list-', '') : null);
      if (presetId) reloadPromptArranger(presetId, 'prompt-arranger');
    }
  });
}

function deletePersonaMedia(imageId) {
  const personaId = document.getElementById('edit-persona-id').value;
  fetch(`/api/personas/${personaId}/images/${imageId}`, {
    method: 'DELETE'
  }).then(r => {
    if(r.ok) {
      const el = document.getElementById(`persona-media-${imageId}`);
      if(el) el.remove();
      htmx.ajax('GET','/partials/personas-modal',{target:'#personas-modal-body',swap:'innerHTML'});
      if (window.CURRENT_CHAT_STATE && window.CURRENT_CHAT_STATE.persona_id === personaId && window.reloadPromptArranger) {
        const presetId = window.CURRENT_CHAT_STATE.preset_id || (document.getElementById('prompt-arranger') && document.querySelector('#prompt-arranger .arranger-list') ? document.querySelector('#prompt-arranger .arranger-list').id.replace('arranger-list-', '') : null);
        if (presetId) reloadPromptArranger(presetId, 'prompt-arranger');
      }
    }
  });
}

function uploadPersonaAvatar(input) {
  if (!input.files || !input.files[0]) return;
  const id = document.getElementById('edit-persona-id').value;

  openCropModal(input.files[0], (croppedBlob) => {
    const formData = new FormData();
    formData.append('file', croppedBlob, 'avatar.png');

    fetch('/api/personas/' + id + '/avatar', {
      method: 'POST',
      body: formData
    }).then(r => r.json()).then(data => {
      const preview = document.getElementById('edit-persona-image-preview');
      const placeholder = document.getElementById('edit-persona-image-placeholder');
      preview.src = '/' + data.avatar_path + '?t=' + new Date().getTime();
      preview.style.display = 'block';
      placeholder.style.display = 'none';

      htmx.ajax('GET','/partials/personas-modal',{target:'#personas-modal-body',swap:'innerHTML'});
    });
  });
  input.value = '';
}

function submitEditPersona(e) {
  e.preventDefault();
  const id = document.getElementById('edit-persona-id').value;
  const data = Object.fromEntries(new FormData(e.target));
  fetch('/api/personas/' + id, {
    method: 'PATCH',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify(data)
  }).then(function(r){
    if(r.ok) {
      closeModal('modal-edit-persona');
      htmx.ajax('GET','/partials/personas-modal',{target:'#personas-modal-body',swap:'innerHTML'});
    }
  });
}
