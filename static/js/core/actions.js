(function () {
  function _resolveAction(name) {
    if (name.indexOf(".") > -1) {
      var parts = name.split(".");
      var fn = window;
      for (var i = 0; i < parts.length; i++) {
        fn = fn[parts[i]];
        if (!fn) return null;
      }
      return typeof fn === "function" ? fn : null;
    }
    return typeof window[name] === "function" ? window[name] : null;
  }

  document.addEventListener("click", function (e) {
    var el = e.target.closest("[data-action]");
    if (!el) return;
    if (el.tagName === 'FORM') return;
    var fn = _resolveAction(el.dataset.action);
    if (fn) fn(el, e);
  });

  window.resolveFormFromEvent = function (e) {
    return e.target.tagName === 'FORM' ? e.target : (e.target.form || e.target.closest('form'));
  };

  document.addEventListener("submit", function (e) {
    var el = e.target.closest("[data-action]");
    if (!el) return;
    var fn = _resolveAction(el.dataset.action);
    if (fn) fn(el, e);
  });

  document.addEventListener("change", function (e) {
    var el = e.target.closest("[data-action]");
    if (!el) return;
    if (el.tagName === 'FORM') return;
    var fn = _resolveAction(el.dataset.action);
    if (fn) fn(el, e);
  });

  document.addEventListener("input", function (e) {
    var el = e.target.closest("[data-action]");
    if (!el) return;
    if (el.tagName === 'FORM') return;
    var fn = _resolveAction(el.dataset.action);
    if (fn) fn(el, e);
  });
})();

/* Action wrappers called from data-action attributes.
   They must NOT shadow the original functions
   (which may be called directly from JS with different signatures). */

window.actionOpenProviderCreateModal = function () {
  openModal("modal-provider-create");
};

window.actionSetActiveProvider = function (el) {
  setActiveProvider(el.dataset.provId, el.dataset.provName, el.dataset.provType);
};

window.actionToggleProviderEdit = function (el) {
  toggleProviderEdit(el.dataset.provId);
};

window.actionSaveProviderModal = function (el, e) {
  e.preventDefault();
  saveProviderModal(e, el.dataset.provId);
};

window.actionOpenThemeModal = function () {
  if (window._saveThemeBackup) window._saveThemeBackup();
  openModal("modal-themes");
};

window.actionOpenFetchModelModal = function (el) {
  openFetchModelModal(el.dataset.provId);
};

window.actionOpenORModelModal = function (el) {
  openORModelModal(el.dataset.provId);
};

window.actionToggleNoFallbacks = function (el) {
  toggleNoFallbacks(el.dataset.provId);
};

window.actionOpenSecretsModal = function (el) {
  openSecretsModal(el.dataset.provId);
};

window.actionCloseModals = function (el, e) {
  if (e.target === el) el.classList.add("hidden");
};

window.actionCloseFetchModels = function () {
  document.getElementById("modal-fetch-models").classList.add("hidden");
};

window.actionCloseSecrets = function () {
  document.getElementById("modal-secrets").classList.add("hidden");
};

window.actionTriggerFileUpload = function (el) {
  document.getElementById(el.dataset.target).click();
};

window.actionCloseModal = function (el, e) {
  if (el.classList.contains("modal-overlay") && e.target !== el) return;
  closeModal(el.dataset.modalId);
};

window.actionOpenTextExpander = function (el) {
  openTextExpander(document.getElementById(el.dataset.targetId), el.dataset.expanderTitle);
};

window.actionCloseExportModal = function () {
  closeModal("modal-export");
};

window.actionCloseEntitySelect = function () {
  closeModal("modal-entity-select");
};

window.actionSetExportType = function (el) {
  if (window.BackupManager) BackupManager.setExportType(el.dataset.etype, el.dataset.exportVal);
};

window.actionToggleExportFlag = function (el) {
  if (window.BackupManager) BackupManager.toggleExportFlag(el.dataset.exportFlag);
};

window.actionImportBackupFile = function (el) {
  if (window.BackupManager) BackupManager.importFile(el);
};

window.actionFilterEntityList = function (el) {
  if (window.BackupManager) BackupManager.filterExportEntities(BackupManager._entitySelectType, el.value);
};

/* Entity edit modal action adapters — bridge between data-action
   and createEditModalHandlers-registered functions. */

window.actionSubmitEditCharacter = function (el, e) {
  e.preventDefault();
  submitEditCharacter(e);
};

window.actionSubmitEditPersona = function (el, e) {
  e.preventDefault();
  submitEditPersona(e);
};

window.actionUploadCharAvatar = function (el) {
  uploadCharacterAvatar(el);
};

window.actionUploadPersonaAvatar = function (el) {
  uploadPersonaAvatar(el);
};

window.actionUploadCharMedia = function (el) {
  uploadCharModalMedia(el);
};

window.actionUploadPersonaMedia = function (el) {
  uploadPersonaMedia(el);
};
