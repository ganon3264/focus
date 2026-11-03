window.api = {
  chats: '/api/chats',
  chat: function (chatId) {
    return '/api/chats/' + chatId;
  },
  chatsStale: '/api/chats/stale',
  chatTrash: '/api/chats/trash',
  chatRestore: function (chatId) {
    return '/api/chats/' + chatId + '/restore';
  },
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
  chatStopSummary: function (chatId) {
    return '/api/chats/' + chatId + '/summarize/stop';
  },
  chatSummary: function (chatId) {
    return '/api/chats/' + chatId + '/summary';
  },
  chatToolStates: function (chatId) {
    return '/api/chats/' + chatId + '/tool-states';
  },
  chatExtensions: function (chatId) {
    return '/api/chats/' + chatId + '/extensions';
  },
  messagePin: function (chatId, msgId) {
    return '/api/chats/' + chatId + '/messages/' + msgId + '/pin';
  },

  characters: function (id) {
    return '/api/characters/' + id;
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
  charBlocksReorder: function (charId) {
    return '/api/characters/' + charId + '/blocks/reorder';
  },
  charBlocksPartial: function (charId) {
    return '/partials/char-blocks/' + charId;
  },
  charBlockPartial: function (charId, blockId) {
    return '/partials/char-block/' + charId + '/' + blockId;
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
  presets: '/api/presets',
  preset: function (id) {
    return '/api/presets/' + id;
  },
  presetBlocks: function (id) {
    return '/api/presets/' + id + '/blocks';
  },
  presetBlock: function (id, blockId) {
    return '/api/presets/' + id + '/blocks/' + blockId;
  },
  presetBlockImage: function (id, blockId, imageId) {
    return '/api/presets/' + id + '/blocks/' + blockId + '/images/' + imageId;
  },
  presetBlockImages: function (id, blockId) {
    return '/api/presets/' + id + '/blocks/' + blockId + '/images';
  },
  presetSettings: function (id) {
    return '/api/presets/' + id + '/settings';
  },
  presetDuplicate: function (id) {
    return '/api/presets/' + id + '/duplicate';
  },
  presetImport: '/api/presets/import',

  providerSecrets: '/api/providers/secrets',
  providerSecret: function (name) {
    return '/api/providers/secrets/' + encodeURIComponent(name);
  },

  stream: '/api/stream',
  stopGeneration: function (messageId) {
    return '/api/stop-generation/' + messageId;
  },

  settings: '/api/settings',
  settingsTheme: '/api/settings/theme',
  settingsActiveProvider: '/api/settings/active-provider',

  themes: '/api/themes',
  theme: function (id) {
    return '/api/themes/' + id;
  },
  themeReset: function (id) {
    return '/api/themes/' + id + '/reset';
  },

  regexScripts: '/api/regex-scripts',
  regexScript: function (id) {
    return '/api/regex-scripts/' + id;
  },
  regexReorder: '/api/regex-scripts/reorder',
  regexPreview: '/api/regex-scripts/preview',

  structuredResponses: '/api/structured-responses',
  structuredResponse: function (id) {
    return '/api/structured-responses/' + id;
  },
  structuredReorder: '/api/structured-responses/reorder',
  structuredPreview: '/api/structured-responses/preview',

  tools: '/api/tools',
  toolsReload: '/api/tools/reload',
  itemize: '/api/itemize',

  extensions: '/api/extensions',
  extensionsReload: '/api/extensions/reload',
  extensionsConfig: '/api/extensions/config',
  extension: function (name) {
    return '/api/extensions/' + encodeURIComponent(name);
  },
  extensionRun: function (name) {
    return '/api/extensions/' + encodeURIComponent(name) + '/run';
  },
  extensionConfig: function (name) {
    return '/api/extensions/' + encodeURIComponent(name) + '/config';
  },
  extensionTest: function (name) {
    return '/api/extensions/' + encodeURIComponent(name) + '/test';
  },

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
    messageToolbars: function (chatId) {
      return '/partials/message-toolbars/' + chatId;
    },
    charactersModal: '/partials/characters-modal',
    personasModal: '/partials/personas-modal',
    providersModal: '/partials/providers-modal',
    secrets: '/partials/secrets',
    presetsModal: '/partials/presets-modal',
    presetArranger: function (presetId) {
      return '/partials/prompt-arranger/' + presetId;
    },
    presetBlock: function (presetId, blockId) {
      return '/partials/prompt-arranger/' + presetId + '/block/' + blockId;
    },
    regexScripts: '/partials/regex-scripts',
    structuredResponses: '/partials/structured-responses',
    exportEntities: '/partials/export-entities',
    chatList: '/partials/chat-list',
  },
};
