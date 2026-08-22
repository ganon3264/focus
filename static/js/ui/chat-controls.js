// Send-button wiring: turns input text / staged files / regen mode into a
// Generation.begin call. Pure UI glue — lifecycle lives in the session.
(function () {
  var sendBtn = document.getElementById('send-btn');
  var input = document.getElementById('chat-input');
  var messageList = document.getElementById('message-list');

  if (!sendBtn || !input || !messageList) return;

  function buildSkeleton() {
    var dataList = document.getElementById('message-list-data');
    var asstDiv = window.buildAssistantSkeleton(
      dataList ? dataList.getAttribute('data-char-name') : 'Assistant',
      dataList ? dataList.getAttribute('data-char-image') : '',
    );
    messageList.insertBefore(asstDiv, window.scrollSentinel);
    return asstDiv;
  }

  sendBtn.addEventListener('click', async function () {
    var chatId = StateManager.get('chat_id');
    var providerId = StateManager.get('provider_id');

    if (sendBtn.dataset.mode === 'regen') {
      if (!providerId) {
        window.showErrorToast('No provider configured. Add one in Providers.');
        return;
      }
      var asstDiv = buildSkeleton();
      asstDiv.scrollIntoView({ behavior: 'smooth' });
      window.Generation.begin(chatId, asstDiv, { isRegen: true });
      return;
    }

    var text = input.value.trim();
    if (!text && (!window.stagedFiles || window.stagedFiles.length === 0)) return;
    if (!providerId) {
      window.showErrorToast('No provider configured. Add one in Providers.');
      return;
    }

    var existingTemp = document.getElementById('temp-user-msg');
    if (existingTemp) existingTemp.remove();

    var dataList = document.getElementById('message-list-data');
    var personaName = dataList ? dataList.getAttribute('data-persona-name') || 'You' : 'You';
    var personaAvatar = dataList ? dataList.getAttribute('data-persona-avatar') : '';

    var userDiv = window.buildUserMessageDiv(text, personaName, personaAvatar, window.stagedFiles);
    messageList.insertBefore(userDiv, window.scrollSentinel);

    var asstDiv = buildSkeleton();
    asstDiv.scrollIntoView({ behavior: 'smooth' });

    input.value = '';
    if (window.resizeTextarea) window.resizeTextarea(input);

    window.Generation.begin(chatId, asstDiv, { isRegen: false, userMessage: text });
  });
})();
