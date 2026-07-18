createEditModalHandlers({
  idPrefix: 'edit-char',
  mediaSectionId: 'edit-char-media-section',
  mediaIdPrefix: 'char-modal-media',
  dataPrefix: 'char',
  stateKey: 'character_id',
  apiGet: function (id) {
    return api.characters(id);
  },
  apiImages: function (id) {
    return api.charImages(id);
  },
  apiImage: function (id, imgId) {
    return api.charImage(id, imgId);
  },
  apiAvatar: function (id) {
    return api.charAvatar(id);
  },
  modalId: 'modal-edit-character',
  modalBodyUrl: '/partials/characters-modal',
  modalBodySelector: '#characters-modal-body',
  openFn: 'openEditCharacterModal',
  uploadFn: 'uploadCharModalMedia',
  uploadFileFn: 'uploadCharModalMediaFile',
  deleteFn: 'deleteCharModalMedia',
  avatarFn: 'uploadCharacterAvatar',
  submitFn: 'submitEditCharacter',
  dropZoneSelector: '#edit-char-media-section',
});
