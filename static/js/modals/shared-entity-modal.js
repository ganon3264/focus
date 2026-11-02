(function () {
  window.setupEntityModal = function (cfg) {

    function resolve(name, fallback) {
      return cfg[name] || fallback;
    }

    var fnDelete = 'promptDelete' + cfg.fnEntity;
    var fnOpenTrash = resolve('openTrashFn', 'open' + cfg.fnEntity + 'TrashModal');
    var fnRestore = 'restore' + cfg.fnEntity;
    var fnHardDelete = 'hardDelete' + cfg.fnEntity;
    var fnSelect = resolve('selectFn', 'select' + cfg.fnEntity + 'Modal');
    var fnImport = resolve('importFn', 'import' + cfg.fnEntity + 'Modal');

    // Hard delete drops the row for good, and chats.
    // character_id/persona_id are ON DELETE SET NULL, so the client selection
    // must be cleared too. Soft delete keeps the link (restorable), so it
    // only invalidates. Falls back to StateManager when the selection entry
    // point is unavailable.
    function clearActiveSelection(id) {
      if (StateManager.get(cfg.stateKey) !== id) return;
      if (cfg.stateKey === 'character_id') {
        if (window.applyCharacter) window.applyCharacter(null);
        else StateManager.setCharacter(null);
      } else if (cfg.stateKey === 'persona_id') {
        if (window.applyPersona) window.applyPersona(null);
        else StateManager.setPersona(null);
      }
    }

    // ----- promptDelete -----
    window[fnDelete] = function (id, name) {
      if (id instanceof Element) {
        name = id.dataset[cfg.nameAttr] || name;
        id = id.dataset[cfg.idAttr];
      }
      var html = '<div class="confirm-text mb-2">Delete ' + cfg.entityLower + ' <strong>' + window.escapeHtml(name) + '</strong>?</div>' +
        '<div class="flex flex-col">' +
        '<label class="row">' +
        '<input type="radio" name="' + cfg.entityLower + '_delete_option" value="soft" checked class="check">' +
        '<span class="row-title">Move ' + cfg.entity + ' to Trash</span>' +
        '<span class="row-meta">Restorable</span></label>';
      if (cfg.deleteWithChats) {
        html += '<label class="row">' +
          '<input type="radio" name="' + cfg.entityLower + '_delete_option" value="soft_with_chats" class="check">' +
          '<span class="row-title">Move ' + cfg.entity + ' &amp; Conversations to Trash</span>' +
          '<span class="row-meta">Hides their chats too</span></label>';
      }
      html += '<label class="row">' +
        '<input type="radio" name="' + cfg.entityLower + '_delete_option" value="hard" class="check">' +
        '<span class="row-title">Delete Forever</span>' +
        '<span class="row-meta">Cannot be undone</span></label>' +
        '</div>';
      window.customConfirm(html, function () {
        var selected = document.querySelector('input[name="' + cfg.entityLower + '_delete_option"]:checked').value;
        var isHard = selected === 'hard';
        var isWithChats = selected === 'soft_with_chats';
        var url;
        if (isHard) {
          url = cfg.apiBase + '/' + id + '?hard=true';
        } else if (isWithChats) {
          url = cfg.apiBase + '/' + id + '?delete_chats=true';
        } else {
          url = cfg.apiBase + '/' + id;
        }
        fetch(url, { method: 'DELETE' }).then(function (r) {
          if (r.ok) {
            var isActive = StateManager.get(cfg.stateKey) === id;
            if (isHard) {
              clearActiveSelection(id);
            } else if (window.Refresh && isActive) {
              Refresh.changed(cfg.stateKey === 'character_id' ? 'characters' : 'personas');
            }
            // Active delete is routed through Refresh (the open grid re-renders
            // via characterCards/personaCards); a targeted inline removal would
            // duplicate it. Non-active (or no registry) still swaps the card out.
            if (!(window.Refresh && isActive)) {
              var card = document.getElementById(cfg.cardPrefix + id);
              if (card) card.remove();
              var grid = document.getElementById(cfg.gridId);
              if (grid && grid.querySelectorAll('[data-ui="entity-row"]').length === 0) {
                grid.innerHTML = '<div class="empty">' + cfg.emptyText + '</div>';
              }
            }
            if (isHard) {
              window.showSuccessToast(name + ' permanently deleted');
            } else {
              var msg = isWithChats ? name + ' & conversations moved to Trash' : name + ' moved to Trash';
              window.showInfoToast(msg);
            }
          }
        });
      });
    };

    // ----- openTrashModal -----
    window[fnOpenTrash] = function () {
      fetch(cfg.apiBase + '/trash')
        .then(function (r) { return r.json(); })
        .then(function (items) {
          var bodyHtml = '<div class="flex flex-col max-h-[60vh] overflow-y-auto">';
          if (items.length === 0) {
            bodyHtml += '<div class="empty">Trash is empty.</div>';
          } else {
            items.forEach(function (item) {
              var imgUrl = item[cfg.imageField];
              var initial = window.escapeHtml((item.name || '?').charAt(0));
              bodyHtml += '<div class="row">';
              if (imgUrl) {
                bodyHtml += '<span class="avatar"><img src="/' + window.escapeHtml(imgUrl) + '" loading="lazy" alt=""></span>';
              } else {
                bodyHtml += '<span class="avatar">' + initial + '</span>';
              }
              bodyHtml +=
                '<span class="row-title">' + window.escapeHtml(item.name) + '</span>' +
                '<span class="row-actions">' +
                '<button class="btn sm" data-id="' + window.escapeHtml(item.id) + '" onclick="' + fnRestore + '(this)">Restore</button>' +
                '<button class="key sm danger" data-id="' + window.escapeHtml(item.id) + '" data-name="' + window.escapeHtml(item.name) + '" onclick="' + fnHardDelete + '(this)" aria-label="Delete forever">' + window.getSvgSprite('trash', 16) + '</button>' +
                '</span></div>';
            });
          }
          bodyHtml += '</div>';

          document.getElementById('modal-trash-body').innerHTML = bodyHtml;
          window.openModal('modal-trash');
        });
    };

    // ----- restore -----
    window[fnRestore] = function (el) {
      var id = el.dataset ? el.dataset.id : el;
      function doRestore(restoreChats) {
        var url = cfg.apiBase + '/' + id + '/restore';
        if (restoreChats !== undefined) {
          url += '?restore_chats=' + restoreChats;
        }
        fetch(url, { method: 'POST' }).then(function (r) {
          if (r.ok) {
            closeModal('modal-trash', { discard: true });
            window.showSuccessToast(cfg.entity + ' restored');
            var g = document.getElementById(cfg.gridId);
            if (g) {
              var cid = StateManager.get(cfg.stateKey) || '';
              var cv = g.dataset.view === 'compact';
              hxGet(cfg.cardEndpoint + id +
                '?current_' + cfg.stateKey + '=' + encodeURIComponent(cid) +
                '&compact_view=' + cv, { target: '#' + cfg.gridId, swap: 'beforeend' })
                .then(function () {
                  var val = localStorage.getItem(cfg.sortStorageKey);
                  if (val && window[cfg.sortFn]) window[cfg.sortFn](val);
                });
            } else {
              hxGet(cfg.modalEndpoint, {
                target: '#' + cfg.modalBodyInnerId,
                swap: 'innerHTML',
              }).then(function () {
                var val = localStorage.getItem(cfg.sortStorageKey);
                if (val && window[cfg.sortFn]) window[cfg.sortFn](val);
              });
            }
          }
        });
      }

      if (cfg.hasRestoreDialog) {
        var html =
          '<div class="confirm-text mb-2">Restore ' + cfg.entityLower + '?</div>' +
          '<label class="row">' +
          '<input type="checkbox" id="restore_chats_cb" checked class="check">' +
          '<span class="row-title">Also restore conversations</span>' +
          '<span class="row-meta">Brings back chats deleted with it</span></label>';
        window.customConfirm(html, function () {
          doRestore(document.getElementById('restore_chats_cb').checked);
        });
      } else {
        doRestore();
      }
    };

    // ----- hardDelete -----
    window[fnHardDelete] = function (el) {
      var id = el.dataset ? el.dataset.id : el;
      var name = el.dataset ? el.dataset.name : '';
      window.customConfirm(
        'Permanently delete <strong>' + window.escapeHtml(name) + '</strong>? This cannot be undone.',
        function () {
          fetch(cfg.apiBase + '/' + id + '?hard=true', { method: 'DELETE' }).then(function (r) {
            if (r.ok) {
              clearActiveSelection(id);
              closeModal('modal-trash', { discard: true });
              window.showSuccessToast(name + ' permanently deleted');
              window[fnOpenTrash]();
            }
          });
        },
      );
    };

    // ----- select -----
    window[fnSelect] = function (el) {
      var id = el.dataset[cfg.idAttr] || '';
      var name = el.dataset[cfg.nameAttr] || '';
      if (cfg.selectMode === 'redirect') {
        window.location.href = (cfg.selectUrl || '/chat') + '?' + cfg.stateKey + '=' + id;
        return;
      }
      closeModal(cfg.modalId);
      if (cfg.stateKey === 'persona_id') {
        window.applyPersona(id, name);
      } else if (cfg.stateKey === 'character_id') {
        window.applyCharacter(id, name);
      } else {
        StateManager['set' + cfg.fnEntity](id);
      }
    };

    // ----- import (optional) -----
    if (cfg.hasImport) {
      window[fnImport] = function (e) {
        e.preventDefault();
        var formData = new FormData(e.target);
        fetch(cfg.apiBase + '/import', {
          method: 'POST',
          body: formData,
        }).then(async function (r) {
          if (r.ok) {
            var data = await r.json();
            window.showImportToast(data, cfg.entityLower + 's');
            var g = document.getElementById(cfg.gridId);
            var cid = StateManager.get(cfg.stateKey) || '';
            var cv = g ? g.dataset.view === 'compact' : false;
            if (g) {
              var fetches = [];
              (data.imported || []).forEach(function (entry) {
                fetches.push(hxGet(cfg.cardEndpoint + entry.id +
                  '?current_' + cfg.stateKey + '=' + encodeURIComponent(cid) +
                  '&compact_view=' + cv, { target: '#' + cfg.gridId, swap: 'beforeend' }));
              });
              Promise.all(fetches).then(function () {
                var val = localStorage.getItem(cfg.sortStorageKey);
                if (val && window[cfg.sortFn]) window[cfg.sortFn](val);
              });
            } else {
              hxGet(cfg.modalEndpoint, {
                target: '#' + cfg.modalBodyInnerId,
                swap: 'innerHTML',
              }).then(function () {
                var val = localStorage.getItem(cfg.sortStorageKey);
                if (val && window[cfg.sortFn]) window[cfg.sortFn](val);
              });
            }
          } else {
            r.text().then(function (t) {
              window.showErrorToast('Import failed: ' + t);
            });
          }
        });
      };
    }
  };
})();
