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

    // ----- promptDelete -----
    window[fnDelete] = function (id, name) {
      if (id instanceof Element) {
        name = id.dataset[cfg.nameAttr] || name;
        id = id.dataset[cfg.idAttr];
      }
      var html = '<div class="mb-4 text-sm" style="color:var(--text);">Delete ' + cfg.entityLower + ' <strong>' + name + '</strong>?</div>' +
        '<div class="flex flex-col gap-3">' +
        '<label class="flex items-start gap-3 cursor-pointer p-3 rounded-lg hover:bg-(--surface-3) transition-colors border border-(--border)">' +
        '<div class="mt-0.5"><input type="radio" name="' + cfg.entityLower + '_delete_option" value="soft" checked class="w-4 h-4 cursor-pointer" style="accent-color: var(--accent);"></div>' +
        '<div class="flex flex-col">' +
        '<span class="text-sm font-bold" style="color:var(--text);">Move ' + cfg.entity + ' to Trash</span>' +
        '<span class="text-xs text-muted">You can restore the ' + cfg.entityLower + ' later.</span></div></label>';
      if (cfg.deleteWithChats) {
        html += '<label class="flex items-start gap-3 cursor-pointer p-3 rounded-lg hover:bg-(--surface-3) transition-colors border border-(--border) relative group">' +
          '<div class="mt-0.5"><input type="radio" name="' + cfg.entityLower + '_delete_option" value="soft_with_chats" class="w-4 h-4 cursor-pointer" style="accent-color: var(--accent);"></div>' +
          '<div class="flex flex-col">' +
          '<span class="text-sm font-bold" style="color:var(--text);">Move ' + cfg.entity + ' &amp; Conversations to Trash</span>' +
          '<span class="text-xs text-muted">Hides their chats too. Both can be restored.</span></div></label>';
      }
      html += '<label class="flex items-start gap-3 cursor-pointer p-3 rounded-lg hover:bg-(--surface-3) transition-colors border border-(--border)">' +
        '<div class="mt-0.5"><input type="radio" name="' + cfg.entityLower + '_delete_option" value="hard" class="w-4 h-4 cursor-pointer" style="accent-color: var(--accent);"></div>' +
        '<div class="flex flex-col">' +
        '<span class="text-sm font-bold" style="color:var(--text);">Delete Forever</span>' +
        '<span class="text-xs text-muted">Permanently delete this ' + cfg.entityLower + '. Cannot be undone.</span></div></label>' +
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
            var card = document.getElementById(cfg.cardPrefix + id);
            if (card) card.remove();
            var grid = document.getElementById(cfg.gridId);
            if (grid && grid.querySelectorAll('.card').length === 0) {
              grid.innerHTML = '<div class="text-muted text-center text-sm py-6 border border-dashed border-(--border) rounded-lg">' + cfg.emptyText + '</div>';
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
          var bodyHtml = '<div class="flex flex-col gap-2 max-h-[60vh] overflow-y-auto pr-1">';
          if (items.length === 0) {
            bodyHtml += '<div class="text-muted text-center py-6 border border-dashed border-(--border) rounded-lg">Trash is empty.</div>';
          } else {
            items.forEach(function (item) {
              var imgUrl = item[cfg.imageField];
              var initial = item.name.charAt(0);
              bodyHtml +=
                '<div class="flex justify-between items-center p-3 border border-(--border) rounded-lg bg-(--surface-2)">' +
                '<div class="flex items-center gap-3">' +
                '<div class="w-10 h-10 rounded-full overflow-hidden bg-(--surface-3) flex items-center justify-center border border-(--border)">';
              if (imgUrl) {
                bodyHtml += '<img src="/' + imgUrl + '" loading="lazy" class="w-full h-full object-cover">';
              } else {
                bodyHtml += '<span class="text-sm font-bold text-muted">' + initial + '</span>';
              }
              bodyHtml +=
                '</div>' +
                '<span class="font-bold text-sm" style="color:var(--text);">' + item.name + '</span>' +
                '</div>' +
                '<div class="flex gap-2">' +
                '<button class="btn btn-secondary btn-sm" onclick="' + fnRestore + '(\'' + item.id + '\')">Restore</button>' +
                '<button class="btn btn-danger btn-sm" onclick="' + fnHardDelete + '(\'' + item.id + '\', \'' + item.name.replace(/'/g, "\\'") + '\')">Delete Forever</button>' +
                '</div></div>';
            });
          }
          bodyHtml += '</div>';

          var modalHtml =
            '<div id="' + cfg.trashModalId + '" class="modal-overlay" role="dialog" aria-modal="true" aria-label="Trash" style="z-index: var(--z-overlay);" onclick="if(event.target===this) this.remove()">' +
            '<div class="modal-content" style="max-width: 500px; width: 90vw;">' +
            '<div class="modal-header" style="margin-bottom: 1rem;">' +
            '<div class="modal-title">Trash Bin</div>' +
            '<button class="btn btn-secondary btn-sm" onclick="document.getElementById(\'' + cfg.trashModalId + '\').remove()" aria-label="Close">' + iconCloseSvg() + '</button>' +
            '</div>' +
            '<div id="' + cfg.trashModalId + '-body">' + bodyHtml + '</div></div></div>';

          document.body.insertAdjacentHTML('beforeend', modalHtml);
        });
    };

    function iconCloseSvg() {
      var tpl = document.getElementById('icon-close-tpl');
      return tpl ? tpl.innerHTML : '';
    }

    // ----- restore -----
    window[fnRestore] = function (id) {
      function doRestore(restoreChats) {
        var url = cfg.apiBase + '/' + id + '/restore';
        if (restoreChats !== undefined) {
          url += '?restore_chats=' + restoreChats;
        }
        fetch(url, { method: 'POST' }).then(function (r) {
          if (r.ok) {
            var modal = document.getElementById(cfg.trashModalId);
            if (modal) modal.remove();
            var g = document.getElementById(cfg.gridId);
            if (g) {
              var cid = StateManager.get(cfg.stateKey) || '';
              var cv = g.dataset.view === 'compact';
              htmx.ajax('GET', cfg.cardEndpoint + id +
                '?current_' + cfg.stateKey + '=' + encodeURIComponent(cid) +
                '&compact_view=' + cv, { target: '#' + cfg.gridId, swap: 'beforeend' })
                .then(function () {
                  var val = localStorage.getItem(cfg.sortStorageKey);
                  if (val && window[cfg.sortFn]) window[cfg.sortFn](val);
                });
            } else {
              htmx.ajax('GET', cfg.modalEndpoint, {
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
          '<div class="mb-4 text-sm" style="color:var(--text);">Restore ' + cfg.entityLower + '?</div>' +
          '<label class="flex items-start gap-3 cursor-pointer p-3 rounded-lg hover:bg-(--surface-3) transition-colors border border-(--border)">' +
          '<div class="mt-0.5"><input type="checkbox" id="restore_chats_cb" checked class="w-4 h-4 cursor-pointer" style="accent-color: var(--accent);"></div>' +
          '<div class="flex flex-col">' +
          '<span class="text-sm font-bold" style="color:var(--text);">Also restore conversations</span>' +
          '<span class="text-xs text-muted">Brings back chats previously deleted with this ' + cfg.entityLower + '.</span></div></label>';
        window.customConfirm(html, function () {
          doRestore(document.getElementById('restore_chats_cb').checked);
        });
      } else {
        doRestore();
      }
    };

    // ----- hardDelete -----
    window[fnHardDelete] = function (id, name) {
      window.customConfirm(
        'Permanently delete <strong>' + name + '</strong>? This cannot be undone.',
        function () {
          fetch(cfg.apiBase + '/' + id + '?hard=true', { method: 'DELETE' }).then(function (r) {
            if (r.ok) {
              var modal = document.getElementById(cfg.trashModalId);
              if (modal) modal.remove();
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
      var card = el.closest('.card');
      if (card) {
        document.querySelectorAll('#' + cfg.gridId + ' .card.active').forEach(function (c) {
          c.classList.remove('active');
        });
        card.classList.add('active');
      }
      if (cfg.selectMode === 'redirect') {
        window.location.href = (cfg.selectUrl || '/chat') + '?' + cfg.stateKey + '=' + id;
      } else {
        StateManager['set' + cfg.fnEntity](id);
        var statusEl = document.getElementById(cfg.statusId);
        if (statusEl) statusEl.textContent = name || '...';
        closeModal(cfg.modalId);
        var chatId = document.getElementById('send-btn')?.dataset?.chatId;
        if (chatId) {
          htmx.ajax('GET', '/partials/message-list/' + chatId, {
            target: '#message-list',
            swap: 'innerHTML',
          });
        }
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
            if (data.errors && data.errors.length) {
              alert(
                'Imported ' + data.imported.length + ' of ' + data.total +
                ' cards.\n\nErrors:\n' +
                data.errors.map(function (e) { return '\u2022 ' + e.filename + ': ' + e.error; }).join('\n'),
              );
            }
            var g = document.getElementById(cfg.gridId);
            var cid = StateManager.get(cfg.stateKey) || '';
            var cv = g ? g.dataset.view === 'compact' : false;
            if (g) {
              var fetches = [];
              (data.imported || []).forEach(function (entry) {
                fetches.push(htmx.ajax('GET', cfg.cardEndpoint + entry.id +
                  '?current_' + cfg.stateKey + '=' + encodeURIComponent(cid) +
                  '&compact_view=' + cv, { target: '#' + cfg.gridId, swap: 'beforeend' }));
              });
              Promise.all(fetches).then(function () {
                var val = localStorage.getItem(cfg.sortStorageKey);
                if (val && window[cfg.sortFn]) window[cfg.sortFn](val);
              });
            } else {
              htmx.ajax('GET', cfg.modalEndpoint, {
                target: '#' + cfg.modalBodyInnerId,
                swap: 'innerHTML',
              }).then(function () {
                var val = localStorage.getItem(cfg.sortStorageKey);
                if (val && window[cfg.sortFn]) window[cfg.sortFn](val);
              });
            }
          } else {
            r.text().then(function (t) { alert('Import failed: ' + t); });
          }
        });
      };
    }
  };
})();
