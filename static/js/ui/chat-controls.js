// Send-button wiring: turns input text / staged files into a Generation.begin
// call. The server decides whether that becomes a new turn or a reply to the
// pending user turn. Pure UI glue — lifecycle lives in the session.
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
    var text = input.value.trim();
    var hasFiles = !!(window.stagedFiles && window.stagedFiles.length > 0);

    var dataList = document.getElementById('message-list-data');
    var lastRole = dataList ? dataList.getAttribute('data-last-role') || '' : '';

    // The server owns whether this is a new turn or a reply to a pending user
    // turn; the button only decides whether there is anything to send at all.
    if (!text && !hasFiles && lastRole !== 'user') return;

    if (!providerId) {
      window.showErrorToast('No provider configured. Add one in Providers.');
      return;
    }

    if (text || hasFiles) {
      var existingTemp = document.getElementById('temp-user-msg');
      if (existingTemp) existingTemp.remove();

      var personaName = dataList ? dataList.getAttribute('data-persona-name') || 'You' : 'You';
      var personaAvatar = dataList ? dataList.getAttribute('data-persona-avatar') : '';

      var userDiv = window.buildUserMessageDiv(text, personaName, personaAvatar, window.stagedFiles);
      messageList.insertBefore(userDiv, window.scrollSentinel);
    }

    var asstDiv = buildSkeleton();
    asstDiv.scrollIntoView({ behavior: 'smooth' });

    input.value = '';
    if (window.resizeTextarea) window.resizeTextarea(input);

    window.Generation.begin(chatId, asstDiv, { isRegen: false, userMessage: text });
  });
})();
