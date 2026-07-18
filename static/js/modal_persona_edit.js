createEditModalHandlers({
  idPrefix: 'edit-persona',
  mediaSectionId: 'edit-persona-media-section',
  mediaIdPrefix: 'persona-media',
  dataPrefix: 'persona',
  stateKey: 'persona_id',
  apiGet: function (id) {
    return api.personas(id);
  },
  apiImages: function (id) {
    return api.personaImages(id);
  },
  apiImage: function (id, imgId) {
    return api.personaImage(id, imgId);
  },
  apiAvatar: function (id) {
    return api.personaAvatar(id);
  },
  modalId: 'modal-edit-persona',
  modalBodyUrl: '/partials/personas-modal',
  modalBodySelector: '#personas-modal-body',
  openFn: 'openEditPersonaModal',
  uploadFn: 'uploadPersonaMedia',
  uploadFileFn: 'uploadPersonaMediaFile',
  deleteFn: 'deletePersonaMedia',
  avatarFn: 'uploadPersonaAvatar',
  submitFn: 'submitEditPersona',
  dropZoneSelector: '#edit-persona-media-section',
});
