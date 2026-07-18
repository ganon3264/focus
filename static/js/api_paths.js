window.api = {
  chats: '/api/chats',
  chat: function(id) { return '/api/chats/' + id; },
  chatAttachments: function(chatId) { return '/api/chats/' + chatId + '/attachments'; },
  chatMessages: function(chatId) { return '/api/chats/' + chatId + '/messages'; },
  chatMessage: function(chatId, msgId) { return '/api/chats/' + chatId + '/messages/' + msgId; },
  chatBulkDelete: function(chatId) { return '/api/chats/' + chatId + '/messages/bulk_delete'; },

  characters: function(id) { return '/api/characters/' + id; },
  charImages: function(charId) { return '/api/characters/' + charId + '/images'; },
  charImage: function(charId, imgId) { return '/api/characters/' + charId + '/images/' + imgId; },
  charAvatar: function(id) { return '/api/characters/' + id + '/avatar'; },

  personas: function(id) { return '/api/personas/' + id; },
  personaImages: function(id) { return '/api/personas/' + id + '/images'; },
  personaImage: function(id, imgId) { return '/api/personas/' + id + '/images/' + imgId; },
  personaAvatar: function(id) { return '/api/personas/' + id + '/avatar'; },

  stream: '/api/stream',

  partials: {
    messageList: function(chatId) { return '/partials/message-list/' + chatId; },
    charactersModal: '/partials/characters-modal',
    personasModal: '/partials/personas-modal',
    providersModal: '/partials/providers-modal',
    promptArranger: function(presetId) { return '/partials/prompt-arranger/' + presetId; },
  }
};
