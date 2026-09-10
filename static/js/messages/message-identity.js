// Single source of truth for message identity.
//
// A message is identified by its bare id, carried on the DOM node as
// `data-message-id`. Two representations are derived from it — never written
// by hand:
//   DOM node     →  #message-<id>
//   pruned stub  →  .message-placeholder[data-msg-id="<id>"]
//
// Anything that needs to translate between them goes through here, so the
// conventions cannot drift apart module by module.
(function () {
  function bare(ref) {
    if (ref == null) return null;
    if (typeof ref === 'string') {
      return ref.indexOf('message-') === 0 ? ref.slice('message-'.length) : ref;
    }
    if (ref.dataset) {
      if (ref.dataset.messageId) return String(ref.dataset.messageId);
      if (ref.dataset.msgId) return String(ref.dataset.msgId);
    }
    return ref.id ? bare(ref.id) : null;
  }

  function domId(ref) {
    var id = bare(ref);
    return id == null ? null : 'message-' + id;
  }

  function node(ref) {
    var dom = domId(ref);
    return dom == null ? null : document.getElementById(dom);
  }

  function placeholder(ref, root) {
    var id = bare(ref);
    if (id == null) return null;
    return (root || document).querySelector('.message-placeholder[data-msg-id="' + id + '"]');
  }

  window.MessageIdentity = {
    bare: bare,
    domId: domId,
    node: node,
    placeholder: placeholder,
  };
})();
