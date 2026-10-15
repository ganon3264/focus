(function () {
  // Central resource -> UI-surface invalidation.
  //
  // This is the single place that records which UI surfaces depend on which
  // server resources. Mutation sites declare the resource they wrote:
  //
  //   Refresh.mutate(url, opts, { changed: ['presets'] });
  //   Refresh.changed('regex_scripts');
  //
  // ...and every surface whose deps include that resource is re-fetched once
  // per tick, deduped and cover-collapsed.
  //
  // A surface is { deps, load, guard?, when?, covers? }:
  //   deps   - resources that make it stale
  //   load   - refetch/re-render function, resolved lazily by name on window
  //   guard  - 'not-streaming' to skip while a generation is running
  //   when   - predicate; flush skips the surface when false (explicit
  //            Refresh.load() ignores it)
  //   covers - surfaces this one already re-renders, dropped from the same
  //            flush so the same region is not fetched twice

  var RESOURCES = [
    'chats', 'messages', 'characters', 'personas', 'presets', 'preset_blocks',
    'preset_variables', 'providers', 'themes', 'regex_scripts',
    'structured_responses', 'extensions', 'tools', 'settings', 'backups',
  ];

  function fn(name) {
    return typeof window[name] === 'function' ? window[name] : null;
  }

  function chatId() {
    return window.StateManager ? StateManager.get('chat_id') : null;
  }

  function presetId() {
    return window.StateManager ? StateManager.get('preset_id') : null;
  }

  function modalOpen(id) {
    return !!(window.ModalController && window.ModalController.isOpen(id));
  }

  function advancedOpen() {
    return modalOpen('modal-advanced');
  }

  function streaming() {
    return !!(window.Generation && window.Generation.isActive && window.Generation.isActive());
  }

  var SURFACES = {
    messages: {
      deps: ['chats', 'messages', 'characters', 'personas', 'presets', 'preset_blocks',
        'preset_variables', 'regex_scripts'],
      guard: 'not-streaming',
      covers: ['chatList'],
      load: function () {
        var cid = chatId();
        var reload = fn('refreshChatMessages');
        if (cid && reload) return reload(cid);
      },
    },
    messageToolbars: {
      deps: ['extensions'],
      guard: 'not-streaming',
      load: function () {
        var cid = chatId();
        var r = fn('refreshMessageToolbars');
        if (cid && r) return r(cid);
      },
    },
    chatList: {
      deps: ['chats', 'characters'],
      load: function () {
        var reload = fn('_refreshChatList');
        if (reload) return reload(chatId() || null);
      },
    },
    selection: {
      deps: ['chats', 'characters', 'personas', 'presets', 'preset_blocks',
        'preset_variables', 'providers'],
      covers: ['chatList', 'presetSelector', 'arranger', 'presetVariables'],
      load: function () {
        var reload = fn('reloadSelectionState');
        if (reload) return reload();
      },
    },
    presetSelector: {
      deps: ['presets', 'chats'],
      covers: ['chatList'],
      load: function () {
        var reload = fn('refreshPresetList');
        if (reload) return reload();
      },
    },
    arranger: {
      deps: ['presets', 'preset_blocks', 'characters', 'personas'],
      load: function () {
        var pid = presetId();
        var reload = fn('reloadPromptArranger');
        if (pid && reload) return reload(pid);
      },
    },
    presetVariables: {
      deps: ['presets', 'preset_blocks', 'preset_variables'],
      load: function () {
        var pid = presetId();
        var reload = fn('reloadPresetVariables');
        if (pid && reload) return reload(pid);
      },
    },
    regexList: {
      // Editing rows is handled in place (per-row swaps), so the list is only
      // context-scoped here; explicit Refresh.load()/reloadRegexScripts() own
      // structural rebuilds. Avoids a full-list flash on every field blur.
      deps: ['presets'],
      when: advancedOpen,
      load: function () {
        var reload = fn('reloadRegexScripts');
        if (reload) return reload();
      },
    },
    structuredList: {
      deps: ['presets'],
      when: advancedOpen,
      load: function () {
        var reload = fn('reloadStructuredResponses');
        if (reload) return reload();
      },
    },
    tools: {
      // In-modal state edited in place; reload only on open / chat change.
      deps: ['chats'],
      when: advancedOpen,
      load: function () {
        var reload = fn('reloadToolsState');
        if (reload) return reload();
      },
    },
    extensions: {
      deps: ['chats'],
      when: advancedOpen,
      load: function () {
        var reload = fn('reloadExtensionsState');
        if (reload) return reload();
      },
    },
    characterCards: {
      deps: ['characters'],
      when: function () { return modalOpen('modal-characters'); },
      load: function () {
        var reload = fn('reloadCharacterCards');
        if (reload) return reload();
      },
    },
    personaCards: {
      deps: ['personas'],
      when: function () { return modalOpen('modal-personas'); },
      load: function () {
        var reload = fn('reloadPersonaCards');
        if (reload) return reload();
      },
    },
    backups: {
      deps: ['backups'],
      when: advancedOpen,
      load: function () {
        return window.BackupManager ? BackupManager.loadList() : undefined;
      },
    },
    themes: {
      deps: ['themes', 'settings'],
      load: function () {
        var reload = fn('refreshThemes');
        if (reload) return reload();
      },
    },
  };

  var pending = Object.create(null);
  var scheduled = null;

  function resolve(resources) {
    var picked = Object.create(null);
    var name;
    for (name in SURFACES) {
      var deps = SURFACES[name].deps;
      for (var i = 0; i < deps.length; i++) {
        if (resources[deps[i]]) { picked[name] = true; break; }
      }
    }
    // Drop covered surfaces; settle transitively in case a covered surface in
    // turn covers another.
    var changed = true;
    while (changed) {
      changed = false;
      for (name in picked) {
        var covers = SURFACES[name].covers;
        if (!covers) continue;
        for (var j = 0; j < covers.length; j++) {
          if (picked[covers[j]]) { delete picked[covers[j]]; changed = true; }
        }
      }
    }
    return picked;
  }

  function flush() {
    var resources = pending;
    pending = Object.create(null);

    if (window.DEBUG) {
      var missed = [];
      for (var r in resources) {
        var hit = false;
        for (var n in SURFACES) {
          if (SURFACES[n].deps.indexOf(r) !== -1) { hit = true; break; }
        }
        if (!hit) missed.push(r);
      }
      if (missed.length) {
        console.warn('[refresh] no surface depends on: ' + missed.join(', '));
      }
    }

    var picked = resolve(resources);
    var jobs = [];
    for (var name in picked) {
      var surface = SURFACES[name];
      if (surface.guard === 'not-streaming' && streaming()) continue;
      if (surface.when && !surface.when()) continue;
      var out = surface.load && surface.load();
      if (out && typeof out.then === 'function') jobs.push(out);
    }
    return Promise.all(jobs);
  }

  function changed() {
    for (var i = 0; i < arguments.length; i++) {
      if (arguments[i]) pending[arguments[i]] = true;
    }
    if (!scheduled) {
      scheduled = Promise.resolve().then(function () {
        scheduled = null;
        return flush();
      });
    }
    return scheduled;
  }

  // Run a mutation through hxFetch (so it shares the partial-fetch queue) and
  // invalidate the declared resources once it commits.
  function mutate(url, opts, spec) {
    var resources = (spec && spec.changed) || [];
    var send = window.hxFetch || window.fetch;
    return send(url, opts).then(function (resp) {
      if (resp && resp.ok && resources.length) changed.apply(null, resources);
      return resp;
    });
  }

  window.Refresh = {
    changed: changed,
    load: function (name) {
      var surface = SURFACES[name];
      if (!surface || !surface.load) return Promise.resolve();
      var out = surface.load();
      return out && typeof out.then === 'function' ? out : Promise.resolve(out);
    },
    mutate: mutate,
    flush: flush,
    surfaces: SURFACES,
    resources: RESOURCES,
  };
})();
