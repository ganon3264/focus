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
  openProviderCreateModal();
};

window.actionSubmitProviderForm = function (el, e) {
  submitProviderForm(el, e);
};

window.actionSetActiveProvider = function (el) {
  setActiveProvider(el.dataset.provId, el.dataset.provName, el.dataset.provType);
};

window.actionOpenThemeModal = function () {
  if (window._saveThemeBackup) window._saveThemeBackup();
  openModal("modal-themes");
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

/* Message toolbar action adapters — bridge between data-action
   and message-level generation/branch/edit/delete functions. */ 

window.actionTriggerRegeneration = function (el) {
  var msg = el.closest('.message');
  var chatId = msg.dataset.chatId;
  window.triggerGeneration(chatId, msg, true);
};

window.actionContinueGeneration = function (el) {
  var msg = el.closest('.message');
  var chatId = msg.dataset.chatId;
  window.triggerGeneration(chatId, msg, true,
    msg.dataset.rawContent || '', msg.dataset.rawReasoning || '');
};

window.actionBranchMessage = function (el) {
  var msg = el.closest('.message');
  window.branchFromMessage(msg.dataset.messageId, msg.dataset.chatId);
};

window.actionEditMessage = function (el) {
  var msg = el.closest('.message');
  window.editMessage(msg.dataset.messageId, msg.dataset.chatId);
};

window.actionEnterDeleteMode = function (el) {
  var msg = el.closest('.message');
  window.enterDeleteMode(msg.dataset.messageId);
};

window.actionToggleReasoning = function (el) {
  window.toggleReasoning(el);
};

window.actionUpdateDeleteSelection = function () {
  updateDeleteSelection();
};

window.actionSwipePrev = function (event, el) {
  var msg = el.closest('.message');
  window.refreshSingleMessage(msg.dataset.chatId, msg.dataset.messageId);
};

window.actionSwipeNext = function (event, el) {
  var msgId = el.closest('[data-message-id]').dataset.messageId;
  window.handleSwipeNext(event, msgId);
};
