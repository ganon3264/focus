(function () {
  // Selection entry points. StateManager is the single source of truth.
  //
  // applyX(): mutate StateManager (which persists to the DB), do immediate
  // synchronous DOM sync, then — after the persist PATCH commits — reload all
  // selection-dependent panes in one server-rendered OOB response
  // (/partials/selection-state). Message-list reloads separately for
  // persona/character changes, where macro resolution changes message display.

  function byId(id) {
    return document.getElementById(id);
  }

  function updateAddVarBtn(id) {
    var btn = byId('preset-add-var-btn');
    if (!btn) return;
    if (id) {
      btn.dataset.presetId = id;
      btn.classList.remove('hidden');
    } else {
      btn.classList.add('hidden');
    }
  }

  function syncSelectorSelection(attempt) {
    attempt = attempt || 0;
    var wrapper = byId('preset-selector-wrapper');
    if (!wrapper || !window.Alpine) return;
    var state = Alpine.$data(wrapper);
    if (!state) {
      // htmx swaps the DOM before Alpine re-initializes the new x-data
      // component. Retry until ready, then derive selection from StateManager
      // (never from the server-rendered value).
      if (attempt < 10) setTimeout(function () { syncSelectorSelection(attempt + 1); }, 0);
      return;
    }
    var id = StateManager.get('preset_id');
    if (id) {
      var item = wrapper.querySelector('[data-preset-id="' + id + '"]');
      state.selectedId = id;
      state.selectedName = item
        ? item.querySelector('.preset-item-name').textContent
        : state.selectedName;
    } else {
      state.selectedId = '';
      state.selectedName = '— Select Preset —';
    }
  }

  function updateStatus(elId, name) {
    if (name == null) return;
    var el = byId(elId);
    if (el) {
      el.textContent = name;
      el.title = name;
    }
  }

  function syncCardHighlight(cfg) {
    var grid = byId(cfg.gridId);
    if (!grid) return;
    var cards = grid.querySelectorAll('.card.active');
    for (var i = 0; i < cards.length; i++) cards[i].classList.remove('active');
    var id = StateManager.get(cfg.stateKey);
    if (id) {
      var card = byId(cfg.cardPrefix + id);
      if (card) card.classList.add('active');
    }
  }

  function syncProviderHighlight(id) {
    var cards = document.querySelectorAll('.provider-card');
    for (var i = 0; i < cards.length; i++) cards[i].classList.remove('active');
    if (id) {
      var card = byId('prov-card-' + id);
      if (card) card.classList.add('active');
    }
  }

  function selectionStateUrl() {
    var parts = [];
    var chatId = StateManager.get('chat_id');
    if (chatId) parts.push('chat_id=' + encodeURIComponent(chatId));
    var presetId = StateManager.get('preset_id');
    if (presetId) parts.push('preset_id=' + encodeURIComponent(presetId));
    var charId = StateManager.get('character_id');
    if (charId) parts.push('character_id=' + encodeURIComponent(charId));
    var personaId = StateManager.get('persona_id');
    if (personaId) parts.push('persona_id=' + encodeURIComponent(personaId));
    return '/partials/selection-state?' + parts.join('&');
  }

  function reloadSelectionState() {
    return hxGet(selectionStateUrl(), {
      target: 'body',
      swap: 'none',
    });
  }

  function reloadMessageList() {
    var chatId = StateManager.get('chat_id');
    if (!chatId || !byId('message-list')) return Promise.resolve();
    return hxGet('/partials/message-list/' + chatId, {
      target: '#message-list',
      swap: 'innerHTML',
    });
  }

  function afterPersist(persist, reloadMessages) {
    return (persist || Promise.resolve())
      .then(function () {
        var jobs = [reloadSelectionState()];
        if (reloadMessages) jobs.push(reloadMessageList());
        return Promise.all(jobs);
      })
      .catch(function (err) {
        if (window.console && console.error) console.error('Selection reload failed', err);
      });
  }

  window.applyPreset = function (id) {
    var persist = StateManager.setPreset(id || null);
    updateAddVarBtn(StateManager.get('preset_id'));
    syncSelectorSelection();
    afterPersist(persist, false);
  };

  window.applyCharacter = function (id, name) {
    var persist = StateManager.setCharacter(id || null);
    updateStatus('status-character', name);
    syncCardHighlight({ gridId: 'char-modal-grid', stateKey: 'character_id', cardPrefix: 'char-card-' });
    afterPersist(persist, true);
  };

  window.applyPersona = function (id, name) {
    var persist = StateManager.setPersona(id || null);
    updateStatus('status-persona', name);
    syncCardHighlight({ gridId: 'persona-modal-grid', stateKey: 'persona_id', cardPrefix: 'persona-card-' });
    afterPersist(persist, true);
  };

  window.applyProvider = function (id, type, name) {
    StateManager.setProvider(id, type);
    syncProviderHighlight(id);
    if (name && window.showInfoToast) window.showInfoToast('Provider: ' + name);
  };

  // Reloads just the preset selector list after presets are added/removed.
  // Selection changes go through applyPreset (full selection-state reload),
  // which already re-renders the selector from the current DB list.
  window.refreshPresetList = function () {
    var chatId = StateManager.get('chat_id') || '';
    return hxGet('/partials/preset-selector?chat_id=' + encodeURIComponent(chatId), {
      target: '#preset-selector',
      swap: 'innerHTML',
    }).then(function () {
      syncSelectorSelection();
    });
  };

  window.updateAddVarBtn = updateAddVarBtn;
  window.syncSelectorSelection = syncSelectorSelection;
  window.updateStatus = updateStatus;
  window.syncCardHighlight = syncCardHighlight;
  window.syncProviderHighlight = syncProviderHighlight;
})();
