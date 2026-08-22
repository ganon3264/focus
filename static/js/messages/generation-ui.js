(function () {
  var sendBtn = document.getElementById('send-btn');
  var stopBtn = document.getElementById('stop-btn');

  window.setGeneratingUI = function (generating) {
    var attachBtn = document.getElementById('attach-btn');
    if (generating) {
      sendBtn.classList.add('hidden');
      stopBtn.classList.remove('hidden');
      var fu = document.getElementById('file-upload');
      if (fu) fu.disabled = true;
      if (attachBtn) attachBtn.disabled = true;
    } else {
      sendBtn.classList.remove('hidden');
      stopBtn.classList.add('hidden');
      var fu = document.getElementById('file-upload');
      if (fu) fu.disabled = false;
      if (attachBtn) attachBtn.disabled = false;
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
        // Sit inline at the end of the last text block — appended to the
        // content div itself it would land on its own line below the <p>.
        var textBlocks = contentDiv.querySelectorAll('p, li, h1, h2, h3, h4, h5, h6');
        if (textBlocks.length) {
          textBlocks[textBlocks.length - 1].appendChild(pulse);
        } else {
          contentDiv.appendChild(pulse);
        }
      }
    } else {
      var contentDivs = asstDiv.querySelectorAll('.message-content');
      for (var j = 0; j < contentDivs.length; j++) contentDivs[j].remove();
    }
  };
})();
