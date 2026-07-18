(function () {
  window.openModal = function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('hidden');
    if (id === 'modal-characters')
      htmx.ajax('GET', window.api.partials.charactersModal + '?current_character_id=' + (StateManager.get('character_id') || ''), { target: '#characters-modal-body', swap: 'innerHTML' });
    else if (id === 'modal-personas')
      htmx.ajax('GET', window.api.partials.personasModal + '?current_persona_id=' + (StateManager.get('persona_id') || ''), { target: '#personas-modal-body', swap: 'innerHTML' });
    else if (id === 'modal-providers')
      htmx.ajax('GET', window.api.partials.providersModal, { target: '#providers-modal-body', swap: 'innerHTML' });
    if (id === 'modal-backups' && window.BackupManager) {
      BackupManager.loadList();
    }
  };

  window.closeModal = function (id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  };
})();
