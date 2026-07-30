(function () {
  var sendBtn = document.getElementById('send-btn');
  var stopBtn = document.getElementById('stop-btn');

  window.setGeneratingUI = function (generating) {
    if (generating) {
      sendBtn.classList.add('hidden');
      stopBtn.classList.remove('hidden');
      var fu = document.getElementById('file-upload');
      if (fu) fu.disabled = true;
    } else {
      window._generating = false;
      window._streamingMessageId = null;
      sendBtn.classList.remove('hidden');
      stopBtn.classList.add('hidden');
      var fu = document.getElementById('file-upload');
      if (fu) fu.disabled = false;
    }
  };

  window.clearStaleContent = function (asstDiv, continueText, continueReasoning) {
    if (!asstDiv) return;
    var staleCalls = asstDiv.querySelectorAll('.tool-calls-stream');
    for (var si = 0; si < staleCalls.length; si++) staleCalls[si].remove();
    var staleSections = asstDiv.querySelectorAll('.tool-calls-section');
    for (var si = 0; si < staleSections.length; si++) staleSections[si].remove();

    var staleBlocks = asstDiv.querySelectorAll('.reasoning-block');
    for (var k = 0; k < staleBlocks.length; k++) staleBlocks[k].remove();

    var reasoningBtn = asstDiv.querySelector('.reasoning-toggle-btn');
    if (reasoningBtn) reasoningBtn.classList.add('hidden');
    asstDiv.classList.remove('reasoning-open');

    // Spinner may be missing because swipe/continue reuse server HTML which has no spinner
    var spinner = asstDiv.querySelector('.message-spinner');
    if (!spinner) {
      spinner = document.createElement('div');
      spinner.className = 'message-spinner';
      asstDiv.appendChild(spinner);
    }
    spinner.classList.remove('hidden');

    if (continueText || continueReasoning) {
      var contentDiv = asstDiv.querySelector('.message-content');
      if (!contentDiv) {
        contentDiv = document.createElement('div');
        contentDiv.className = 'message-content markdown-content processed pl-stream';
        var bodyEl = asstDiv.querySelector('.message-body');
        if (bodyEl) bodyEl.appendChild(contentDiv);
      }
      if (continueText) {
        var pulse = document.createElement('span');
        pulse.className = 'gen-pulse';
        contentDiv.appendChild(pulse);
      }
    } else {
      var contentDivs = asstDiv.querySelectorAll('.message-content');
      for (var j = 0; j < contentDivs.length; j++) contentDivs[j].remove();
    }
  };
})();
