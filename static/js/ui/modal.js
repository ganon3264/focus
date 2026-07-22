(function () {
  window.openModal = function (id) {
    var el = document.getElementById(id);
    if (!el) return;
    el.classList.remove('hidden');

    function needsFetch(targetId) {
      var inner = document.querySelector(targetId);
      return !inner || !inner.children.length || inner.children[0].textContent === 'Loading…';
    }

    if (id === 'modal-characters') {
      if (needsFetch('#characters-modal-body-inner'))
        htmx.ajax('GET', window.api.partials.charactersModal + '?current_character_id=' + (StateManager.get('character_id') || ''), { target: '#characters-modal-body-inner', swap: 'innerHTML' });
    } else if (id === 'modal-personas') {
      if (needsFetch('#personas-modal-body-inner'))
        htmx.ajax('GET', window.api.partials.personasModal + '?current_persona_id=' + (StateManager.get('persona_id') || ''), { target: '#personas-modal-body-inner', swap: 'innerHTML' });
    } else if (id === 'modal-providers') {
      htmx.ajax('GET', window.api.partials.providersModal, { target: '#providers-modal-body-inner', swap: 'innerHTML' });
    }
    if (id === 'modal-backups' && window.BackupManager) {
      BackupManager.loadList();
    }
  };

  window.closeModal = function (id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('hidden');
  };
})();
