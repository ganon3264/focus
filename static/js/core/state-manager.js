(function () {
  var STATE = {
    character_id: null,
    persona_id: null,
    preset_id: null,
    provider_id: null,
    provider_type: null,
    chat_id: null,
    multimodal_enabled: null,
  };
  var LISTENERS = {};

  function emit(event, data) {
    (LISTENERS[event] || []).forEach(function (fn) {
      fn(data);
    });
    if (window.dispatchEvent && window.CustomEvent) {
      window.dispatchEvent(new CustomEvent(event, { detail: data }));
    }
  }

  window.StateManager = {
    init: function (state, chatId) {
      STATE = Object.assign(
        {
          character_id: null,
          persona_id: null,
          preset_id: null,
          provider_id: null,
          provider_type: null,
          chat_id: null,
          multimodal_enabled: null,
        },
        state,
      );
      if (chatId) STATE.chat_id = chatId;
      if (!STATE.provider_id) {
        STATE.provider_id = localStorage.getItem('focus-provider-id') || null;
      }
      if (!STATE.provider_type) {
        STATE.provider_type = localStorage.getItem('focus-provider-type') || null;
      }
    },

    on: function (event, fn) {
      if (!LISTENERS[event]) LISTENERS[event] = [];
      LISTENERS[event].push(fn);
    },

    off: function (event, fn) {
      var arr = LISTENERS[event];
      if (arr) {
        var idx = arr.indexOf(fn);
        if (idx >= 0) arr.splice(idx, 1);
      }
    },

    get: function (key) {
      return STATE[key];
    },

    getAll: function () {
      return {
        character_id: STATE.character_id,
        persona_id: STATE.persona_id,
        preset_id: STATE.preset_id,
        provider_id: STATE.provider_id,
        provider_type: STATE.provider_type,
      };
    },

    _persist: function (changes) {
      if (!STATE.chat_id) return null;
      return fetch('/api/chats/' + STATE.chat_id, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(changes),
      });
    },

    _persistProvider: function (id, type) {
      fetch('/api/settings/active-provider', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: id, provider_type: type }),
      });
      if (id) localStorage.setItem('focus-provider-id', id);
      else localStorage.removeItem('focus-provider-id');
      if (type) localStorage.setItem('focus-provider-type', type);
      else localStorage.removeItem('focus-provider-type');
    },

    setCharacter: function (id) {
      var prev = STATE.character_id;
      STATE.character_id = id || null;
      var p = this._persist({ character_id: STATE.character_id });
      emit('character-changed', { prev: prev, value: STATE.character_id, persist: p });
      return p;
    },

    setPersona: function (id) {
      var prev = STATE.persona_id;
      STATE.persona_id = id || null;
      var p = this._persist({ persona_id: STATE.persona_id });
      emit('persona-changed', { prev: prev, value: STATE.persona_id, persist: p });
      return p;
    },

    setPreset: function (id) {
      var prev = STATE.preset_id;
      STATE.preset_id = id || null;
      var p = this._persist({ preset_id: STATE.preset_id });
      emit('preset-changed', { prev: prev, value: STATE.preset_id, persist: p });
      return p;
    },

    setProvider: function (id, type) {
      var prevId = STATE.provider_id;
      var prevType = STATE.provider_type;
      STATE.provider_id = id || null;
      STATE.provider_type = type || null;
      this._persistProvider(STATE.provider_id, STATE.provider_type);
      emit('provider-changed', {
        prevId: prevId,
        prevType: prevType,
        id: STATE.provider_id,
        type: STATE.provider_type,
      });
    },

    setChat: function (id) {
      var prev = STATE.chat_id;
      STATE.chat_id = id || null;
      emit('chat-changed', { prev: prev, value: STATE.chat_id });
    },

    setMultimodal: function (enabled) {
      var prev = STATE.multimodal_enabled;
      STATE.multimodal_enabled = !!enabled;
      emit('multimodal-changed', { prev: prev, value: STATE.multimodal_enabled });
    },
  };
})();
