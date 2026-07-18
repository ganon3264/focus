window.api = {
  chats: '/api/chats',
  chat: function (id) {
    return '/api/chats/' + id;
  },
  chatDelete: function (id) {
    return '/api/chats/' + id;
  },
  chatRestore: function (id) {
    return '/api/chats/' + id + '/restore';
  },
  chatTrash: '/api/chats/trash',
  chatAttachments: function (chatId) {
    return '/api/chats/' + chatId + '/attachments';
  },
  chatMessages: function (chatId) {
    return '/api/chats/' + chatId + '/messages';
  },
  chatMessage: function (chatId, msgId) {
    return '/api/chats/' + chatId + '/messages/' + msgId;
  },
  chatBulkDelete: function (chatId) {
    return '/api/chats/' + chatId + '/messages/bulk_delete';
  },
  chatSwipe: function (chatId, msgId) {
    return '/api/chats/' + chatId + '/messages/' + msgId + '/swipe';
  },
  chatBranch: function (chatId, msgId) {
    return '/api/chats/' + chatId + '/messages/' + msgId + '/branch';
  },

  characters: function (id) {
    return '/api/characters/' + id;
  },
  charImport: '/api/characters/import',
  charTrash: '/api/characters/trash',
  charRestore: function (charId, delChats) {
    return '/api/characters/' + charId + '/restore?restore_chats=' + delChats;
  },
  charHardDelete: function (charId) {
    return '/api/characters/' + charId + '?hard=true';
  },
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
  personas_: '/api/personas',
  personaImages: function (id) {
    return '/api/personas/' + id + '/images';
  },
  personaImage: function (id, imgId) {
    return '/api/personas/' + id + '/images/' + imgId;
  },
  personaAvatar: function (id) {
    return '/api/personas/' + id + '/avatar';
  },

  presets: '/api/presets',
  preset: function (id) {
    return '/api/presets/' + id;
  },
  presetImport: '/api/presets/import',
  presetBlocks: function (presetId) {
    return '/api/presets/' + presetId + '/blocks';
  },
  presetBlock: function (presetId, blockId) {
    return '/api/presets/' + presetId + '/blocks/' + blockId;
  },
  presetBlockImages: function (presetId, blockId) {
    return '/api/presets/' + presetId + '/blocks/' + blockId + '/images';
  },
  presetBlockImage: function (presetId, blockId, imageId) {
    return '/api/presets/' + presetId + '/blocks/' + blockId + '/images/' + imageId;
  },

  providers: '/api/providers',
  provider: function (id) {
    return '/api/providers/' + id;
  },
  providerFetchModels: '/api/providers/fetch_models',
  providerORModels: '/api/providers/openrouter/models',
  providerOREndpoint: function (modelId) {
    return '/api/providers/openrouter/endpoints/' + encodeURIComponent(modelId);
  },
  providerBalance: function (id) {
    return '/api/providers/' + id + '/balance';
  },
  providerSecrets: '/api/providers/secrets',
  providerSecret: function (name) {
    return '/api/providers/secrets/' + encodeURIComponent(name);
  },

  settings: '/api/settings',
  setting: function (key) {
    return '/api/settings/' + key;
  },
  activeProvider: '/api/settings/active-provider',
  stream: '/api/stream',
  itemize: '/api/itemize',

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
    singleMessage: function (chatId, msgId) {
      return '/partials/message/' + chatId + '/' + msgId;
    },
    charactersModal: '/partials/characters-modal',
    personasModal: '/partials/personas-modal',
    providersModal: '/partials/providers-modal',
    promptArranger: function (presetId) {
      return '/partials/prompt-arranger/' + presetId;
    },
    singleBlock: function (presetId, blockId) {
      return '/partials/prompt-arranger/' + presetId + '/block/' + blockId;
    },
    presetsModal: '/partials/presets-modal',
    exportEntities: '/partials/export-entities',
    presetEditor: function (presetId) {
      return '/partials/preset-editor/' + presetId;
    },
    presetVariables: function (presetId) {
      return '/partials/preset-variables/' + presetId;
    },
    singleVarGroup: function (presetId, groupName) {
      return '/partials/preset-variables/' + presetId + '/group/' + encodeURIComponent(groupName);
    },
    chatList: '/partials/chat-list',
  },
};
