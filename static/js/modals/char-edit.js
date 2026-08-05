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
  greetings: true,
  greetingPrevFn: 'charGreetingPrev',
  greetingNextFn: 'charGreetingNext',
  greetingAddFn: 'charGreetingAdd',
  greetingDeleteFn: 'charGreetingDelete',
  greetingInputFn: 'charGreetingInput',
  modalId: 'modal-edit-character',
  cardEndpoint: '/partials/character-card/',
  gridId: 'char-modal-grid',
  sortStorageKey: 'focus_char_sort',
  sortFn: 'sortCharacters',
  openFn: 'openEditCharacterModal',
  uploadFn: 'uploadCharModalMedia',
  uploadFileFn: 'uploadCharModalMediaFile',
  deleteFn: 'deleteCharModalMedia',
  avatarFn: 'uploadCharacterAvatar',
  submitFn: 'submitEditCharacter',
  dropZoneSelector: '#edit-char-media-section',
});
