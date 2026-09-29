window.api = {
  chats: '/api/chats',
  chatAttachments: function (chatId) {
    return '/api/chats/' + chatId + '/attachments';
  },
  chatMessage: function (chatId, msgId) {
    return '/api/chats/' + chatId + '/messages/' + msgId;
  },
  chatBulkDelete: function (chatId) {
    return '/api/chats/' + chatId + '/messages/bulk_delete';
  },
  chatBranch: function (chatId, msgId) {
    return '/api/chats/' + chatId + '/messages/' + msgId + '/branch';
  },
  chatSummarize: function (chatId) {
    return '/api/chats/' + chatId + '/summarize';
  },
  chatSummary: function (chatId) {
    return '/api/chats/' + chatId + '/summary';
  },

  characters: function (id) {
    return '/api/characters/' + id;
  },
  charImport: '/api/characters/import',
  charDelete: function (charId, deleteChats) {
    return '/api/characters/' + charId + '?delete_chats=' + deleteChats;
  },
  charImages: function (charId) {
    return '/api/characters/' + charId + '/images';
  },
  charImage: function (charId, imgId) {
    return '/api/characters/' + charId + '/images/' + imgId;
  },
  charAvatar: function (id) {
    return '/api/characters/' + id + '/avatar';
  },
  charBlocks: function (charId) {
    return '/api/characters/' + charId + '/blocks';
  },
  charBlock: function (charId, blockId) {
    return '/api/characters/' + charId + '/blocks/' + blockId;
  },
  charBlockImages: function (charId, blockId) {
    return '/api/characters/' + charId + '/blocks/' + blockId + '/images';
  },
  charBlockImage: function (charId, blockId, imageId) {
    return '/api/characters/' + charId + '/blocks/' + blockId + '/images/' + imageId;
  },

  personas: function (id) {
    return '/api/personas/' + id;
  },
  personaImages: function (id) {
    return '/api/personas/' + id + '/images';
  },
  personaImage: function (id, imgId) {
    return '/api/personas/' + id + '/images/' + imgId;
  },
  personaAvatar: function (id) {
    return '/api/personas/' + id + '/avatar';
  },

  providers: '/api/providers',
  provider: function (id) {
    return '/api/providers/' + id;
  },
  providerFetchModels: '/api/providers/fetch_models',
  providerBalance: function (id) {
    return '/api/providers/' + id + '/balance';
  },
  providerActiveKey: function (id) {
    return '/api/providers/' + id + '/active-key';
  },
  providerOpenRouterCapabilities: function (model) {
    return '/api/providers/openrouter/capabilities?model=' + encodeURIComponent(model);
  },
  providerSecrets: '/api/providers/secrets',
  providerSecret: function (name) {
    return '/api/providers/secrets/' + encodeURIComponent(name);
  },

  stream: '/api/stream',

  cleanDb: '/api/db/clean',
  backups: '/api/backups',
  backupRestore: function (id) {
    return '/api/backups/' + id + '/restore';
  },
  backupDelete: function (id) {
    return '/api/backups/' + id;
  },

  export: '/api/export',
  import_: '/api/import',

  partials: {
    messageList: function (chatId) {
      return '/partials/message-list/' + chatId;
    },
    charactersModal: '/partials/characters-modal',
    personasModal: '/partials/personas-modal',
    providersModal: '/partials/providers-modal',
    exportEntities: '/partials/export-entities',
    chatList: '/partials/chat-list',
  },
};
