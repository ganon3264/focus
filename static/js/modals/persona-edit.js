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
  cardEndpoint: '/partials/persona-modal-card/',
  gridId: 'persona-modal-grid',
  sortStorageKey: 'focus_persona_sort',
  sortFn: 'sortPersonas',
  openFn: 'openEditPersonaModal',
  uploadFn: 'uploadPersonaMedia',
  uploadFileFn: 'uploadPersonaMediaFile',
  deleteFn: 'deletePersonaMedia',
  avatarFn: 'uploadPersonaAvatar',
  submitFn: 'submitEditPersona',
  dropZoneSelector: '#edit-persona-media-section',
});
