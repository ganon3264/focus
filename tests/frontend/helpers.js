// Shared JS test helpers — browser mocks, assertions, DOM builders
// Load via: var h = require('./_helpers.js');

var failures = 0;
var tests = 0;

// ── Assertions ──

function assert(cond, msg) {
  tests++;
  if (!cond) { console.error('FAIL: ' + msg); failures++; }
  else console.log('OK:   ' + msg);
}

function assertEqual(a, b, msg) {
  tests++;
  if (a !== b) {
    console.error('FAIL: ' + msg + ' — expected ' + JSON.stringify(b) + ', got ' + JSON.stringify(a));
    failures++;
  } else console.log('OK:   ' + msg);
}

function assertDeepEqual(a, b, msg) {
  var s = JSON.stringify(a), t = JSON.stringify(b);
  tests++;
  if (s !== t) {
    console.error('FAIL: ' + msg + ' — expected ' + t + ', got ' + s);
    failures++;
  } else console.log('OK:   ' + msg);
}

function assertIncludes(haystack, needle, msg) {
  tests++;
  if (haystack.indexOf(needle) === -1) {
    console.error('FAIL: ' + msg + ' — expected "' + needle + '" not found in output');
    failures++;
  } else console.log('OK:   ' + msg);
}

function assertNotIncludes(haystack, needle, msg) {
  tests++;
  if (haystack.indexOf(needle) !== -1) {
    console.error('FAIL: ' + msg + ' — unexpected "' + needle + '" found in output');
    failures++;
  } else console.log('OK:   ' + msg);
}

// ── Mock localStorage ──

function createMockLocalStorage() {
  var store = {};
  return {
    _store: store,
    getItem: function (k) { return store.hasOwnProperty(k) ? store[k] : null; },
    setItem: function (k, v) { store[k] = String(v); },
    removeItem: function (k) { delete store[k]; },
    clear: function () { store = {}; },
  };
}

// ── Mock fetch ──

function createMockFetch(defaultResponse) {
  defaultResponse = defaultResponse || { ok: true };
  var calls = [];
  var fn = function (url, opts) {
    calls.push({ url: url, opts: opts });
    return Promise.resolve(defaultResponse);
  };
  fn._calls = calls;
  fn._last = function () { return calls[calls.length - 1] || null; };
  fn._reset = function () { calls.length = 0; };
  return fn;
}

// ── Mock CustomEvent ──

function createMockCustomEvent() {
  var events = [];
  var CustomEventCtor = function (name, opts) {
    this.type = name;
    this.detail = opts ? opts.detail : undefined;
  };
  CustomEventCtor._events = events;
  return CustomEventCtor;
}

// ── Mock document ──

function makeElement(tag) {
  var el = {
    tagName: (tag || 'div').toUpperCase(),
    children: [],
    classList: {
      _set: new Set(),
      add: function (c) { this._set.add(c); },
      remove: function (c) { this._set.delete(c); },
      contains: function (c) { return this._set.has(c); },
      toggle: function (c, force) {
        if (force === true) this._set.add(c);
        else if (force === false) this._set.delete(c);
        else if (this._set.has(c)) this._set.delete(c);
        else this._set.add(c);
      },
    },
    _attrs: {},
    style: {},
    parent: null,
    addEventListener: function () {},
    removeEventListener: function () {},
    setAttribute: function (k, v) { this._attrs[k] = v; },
    getAttribute: function (k) { return this._attrs[k]; },
    hasAttribute: function (k) { return k in this._attrs; },
    removeAttribute: function (k) { delete this._attrs[k]; },
    appendChild: function (c) {
      // If already a child, move to end; if it belongs to another parent, real
      // DOM detaches it first.
      var idx = this.children.indexOf(c);
      if (idx >= 0) this.children.splice(idx, 1);
      if (c.parent && c.parent !== this) {
        var pidx = c.parent.children.indexOf(c);
        if (pidx >= 0) c.parent.children.splice(pidx, 1);
      }
      this.children.push(c);
      c.parent = this;
      return c;
    },
    remove: function () {
      if (this.parent) {
        var i = this.parent.children.indexOf(this);
        if (i >= 0) this.parent.children.splice(i, 1);
        this.parent = null;
      }
    },
    cloneNode: function (deep) {
      var copy = makeElement(this.tagName.toLowerCase());
      copy.id = this.id;
      var attrs = this._attrs;
      Object.keys(attrs).forEach(function (k) { copy._attrs[k] = attrs[k]; });
      Array.from(this.classList._set).forEach(function (c) { copy.classList.add(c); });
      if (deep) {
        if (this._textContent != null) copy._textContent = this._textContent;
        if (this._innerHTML != null) copy._innerHTML = this._innerHTML;
        for (var i = 0; i < this.children.length; i++) copy.appendChild(this.children[i].cloneNode(true));
      }
      return copy;
    },
    insertBefore: function (newEl, refEl) {
      // Real DOM moves an already-attached node instead of duplicating it.
      var cur = this.children.indexOf(newEl);
      if (cur >= 0) this.children.splice(cur, 1);
      if (refEl) {
        var idx = this.children.indexOf(refEl);
        if (idx >= 0) this.children.splice(idx, 0, newEl);
        else this.children.push(newEl);
      } else {
        this.children.push(newEl);
      }
      newEl.parent = this;
      return newEl;
    },
    querySelector: function (sel) { return querySelectorAll(this, sel)[0] || null; },
    querySelectorAll: function (sel) { return querySelectorAll(this, sel); },
    matches: function (sel) { return matches(el, sel); },
    closest: function (sel) {
      var n = this;
      while (n) {
        if (matches(n, sel)) return n;
        n = n.parent;
      }
      return null;
    },
    getBoundingClientRect: function () {
      return { top: 0, bottom: 0, left: 0, right: 0, width: 0, height: 0 };
    },
    scrollIntoView: function () {},
  };
  Object.defineProperty(el, 'className', {
    configurable: true,
    get: function () { return Array.from(this.classList._set).join(' '); },
    set: function (v) {
      this.classList._set = new Set(v.trim().split(/\s+/).filter(Boolean));
    },
  });
  Object.defineProperty(el, 'parentNode', {
    get: function () { return el.parent; },
  });
  function _camelToKebab(str) {
    return str.replace(/[A-Z]/g, function (m) { return '-' + m.toLowerCase(); });
  }
  function _kebabToCamel(str) {
    return str.replace(/-([a-z])/g, function (_, c) { return c.toUpperCase(); });
  }
  Object.defineProperty(el, 'dataset', {
    configurable: true,
    get: function () {
      var attrs = el._attrs;
      return new Proxy({}, {
        get: function (_, prop) { return attrs['data-' + _camelToKebab(prop)]; },
        set: function (_, prop, value) { attrs['data-' + _camelToKebab(prop)] = value; return true; },
        deleteProperty: function (_, prop) { delete attrs['data-' + _camelToKebab(prop)]; return true; },
        has: function (_, prop) { return ('data-' + _camelToKebab(prop)) in attrs; },
        ownKeys: function () {
          return Object.keys(attrs).filter(function (k) { return k.startsWith('data-'); }).map(function (k) { return _kebabToCamel(k.slice(5)); });
        },
      });
    },
  });
  Object.defineProperty(el, 'innerHTML', {
    configurable: true,
    get: function () { return el._innerHTML || ''; },
    set: function (v) {
      el._innerHTML = v;
      if (el.tagName === 'TEXTAREA') el._value = _decodeEntities(v);
      el.children = [];
      var re = /<(\w+)([^>]*)>/g;
      var m;
      var lastIdx = 0;
      var createEl = function (tag, attrs) {
        var child = makeElement(tag);
        var cls = /class\s*=\s*"([^"]+)"/.exec(attrs);
        if (cls) cls[1].split(/\s+/).forEach(function (c) { child.classList.add(c); });
        var id = /id\s*=\s*"([^"]+)"/.exec(attrs);
        if (id) child.id = id[1];
        var dataRe = /data-([\w-]+)\s*=\s*"([^"]*)"/g;
        var dataM;
        while ((dataM = dataRe.exec(attrs)) !== null) {
          child.dataset[dataM[1]] = dataM[2];
        }
        return child;
      };
      while ((m = re.exec(v)) !== null) {
        if (m.index > lastIdx) {
          var text = v.substring(lastIdx, m.index);
          var txtEl = makeElement('span');
          txtEl._textContent = text;
          txtEl.isText = true;
          el.children.push(txtEl);
        }
        el.children.push(createEl(m[1], m[2]));
        lastIdx = re.lastIndex;
      }
    },
  });
  Object.defineProperty(el, 'value', {
    configurable: true,
    get: function () { return el._value !== undefined ? el._value : ''; },
    set: function (v) { el._value = v; },
  });
  Object.defineProperty(el, 'firstElementChild', {
    get: function () {
      for (var i = 0; i < el.children.length; i++) {
        if (!el.children[i].isText) return el.children[i];
      }
      return null;
    },
  });
  Object.defineProperty(el, 'nextElementSibling', {
    get: function () {
      if (!el.parent) return null;
      var idx = el.parent.children.indexOf(el);
      for (var i = idx + 1; i < el.parent.children.length; i++) {
        if (!el.parent.children[i].isText) return el.parent.children[i];
      }
      return null;
    },
  });
  Object.defineProperty(el, 'textContent', {
    configurable: true,
    get: function () { return el._textContent || ''; },
    set: function (v) { el._textContent = v; el.children = []; },
  });
  return el;
}

function _decodeEntities(html) {
  return String(html)
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&amp;/g, '&');
}

function _matchesSimple(el, sel) {
  if (sel[0] === '.' && !/[\[ :#]/.test(sel) && sel.indexOf('.', 1) === -1) return el.classList.contains(sel.slice(1));
  if (sel[0] === '#' && sel.indexOf('[') === -1 && sel.indexOf('.') === -1) return el.id === sel.slice(1);
  return null;
}

function matches(el, sel) {
  if (!el || !el.tagName) return false;
  if (sel === '*') return true;
  // Handle :not(selector)
  var notMatch = /:not\(([^)]+)\)/.exec(sel);
  if (notMatch) {
    var inner = notMatch[1];
    var base = sel.replace(notMatch[0], '');
    if (base && !matches(el, base)) return false;
    return !matches(el, inner);
  }
  // Strip pseudo-selectors like :checked before further matching
  var pseudoRe = /:(\w[\w-]*)/;
  var pseudoMatch = pseudoRe.exec(sel);
  if (pseudoMatch) {
    var pseudoName = pseudoMatch[1];
    var pseudoResult;
    if (pseudoName === 'checked') pseudoResult = !!(el.checked);
    else return false; // unknown pseudo, no match
    if (!pseudoResult) return false;
    sel = sel.slice(0, pseudoMatch.index) + sel.slice(pseudoMatch.index + pseudoMatch[0].length);
    if (!sel) return true; // only pseudo was checked and it passed
    // Fall through to match the base selector (sel is now e.g. ".msg-select-checkbox")
  }
  // Try simple .class and #id selectors
  var simple = _matchesSimple(el, sel);
  if (simple !== null) return simple;
  // Handle [attr] (presence-only) selector
  var boolAttrRe = /\[(\w[\w-]*)\]/;
  var boolMatch = boolAttrRe.exec(sel);
  if (boolMatch) {
    var boolSel = boolMatch[0];
    var boolName = boolMatch[1];
    var baseSel2 = sel.slice(0, boolMatch.index) + sel.slice(boolMatch.index + boolSel.length);
    if (baseSel2) {
      if (!matches(el, baseSel2)) return false;
    }
    if (!el.hasAttribute(boolName)) return false;
    return true;
  }
  // Handle [attr="value"] and [attr~="value"] (whitespace-token) selectors
  var attrRe = /\[(\w[\w-]*)\s*(~?)=\s*"([^"]*)"\]/;
  var attrMatch = attrRe.exec(sel);
  if (attrMatch) {
    var attrSel = attrMatch[0];
    var attrName = attrMatch[1];
    var attrOp = attrMatch[2];
    var attrVal = attrMatch[3];
    var baseSel = sel.slice(0, attrMatch.index) + sel.slice(attrMatch.index + attrSel.length);
    if (baseSel) {
      if (!matches(el, baseSel)) return false;
    }
    var actual = el.getAttribute(attrName);
    if (attrOp === '~') {
      if (!actual) return false;
      return actual.trim().split(/\s+/).indexOf(attrVal) !== -1;
    }
    if (actual !== attrVal) return false;
    return true;
  }
  var parts = sel.split(/(?=[#.])/);
  // When the selector starts with . or #, the split may drop the leading empty
  // string (Node v24+), so parts[0] would be ".cls" instead of "".  Detect this.
  var tag = (parts[0] && parts[0][0] !== '.' && parts[0][0] !== '#') ? parts[0] : '';
  if (tag && tag !== el.tagName.toLowerCase() && tag !== el.tagName) return false;
  for (var i = 1; i < parts.length; i++) {
    if (parts[i][0] === '.') {
      if (!el.classList.contains(parts[i].slice(1))) return false;
    } else if (parts[i][0] === '#') {
      if (el.id !== parts[i].slice(1)) return false;
    }
  }
  return true;
}

function querySelectorAll(root, sel) {
  var results = [];
  function walk(el) {
    if (el && el.tagName && matches(el, sel)) results.push(el);
    if (el && el.children) {
      for (var i = 0; i < el.children.length; i++) walk(el.children[i]);
    }
  }
  walk(root);
  return results;
}

// ── <template> support ──
// The fake DOM's innerHTML setter is flat (it drops nesting), so template
// content is parsed with a nesting-aware parser instead. Template content is
// never part of the host tree, mirroring the real inert behaviour.

var VOID_TAGS = { img: 1, source: 1, input: 1, br: 1, hr: 1, meta: 1, link: 1 };

function _parseAttrs(el, raw) {
  var re = /([\w:@.-]+)(?:\s*=\s*"([^"]*)"|\s*=\s*'([^']*)'|\s*=\s*([^\s"'>]+))?/g;
  var m;
  while ((m = re.exec(raw || '')) !== null) {
    var name = m[1];
    var value = m[2] !== undefined ? m[2] : m[3] !== undefined ? m[3] : m[4] !== undefined ? m[4] : '';
    if (name === 'class') {
      value.split(/\s+/).filter(Boolean).forEach(function (c) { el.classList.add(c); });
    } else if (name === 'id') {
      el.id = value;
    } else {
      el.setAttribute(name, value);
    }
  }
}

function parseHtmlTree(html) {
  var root = makeElement('div');
  var stack = [root];
  var tokenRe = /<(\/?)([a-zA-Z][\w-]*)((?:"[^"]*"|'[^']*'|[^>])*?)(\/?)>/g;
  var last = 0;
  var m;

  function pushText(text) {
    if (!text || !text.trim()) return;
    var node = makeElement('span');
    node.isText = true;
    node.textContent = text;
    stack[stack.length - 1].appendChild(node);
  }

  while ((m = tokenRe.exec(html)) !== null) {
    pushText(html.slice(last, m.index));
    last = tokenRe.lastIndex;
    var closing = m[1] === '/';
    var tag = m[2].toLowerCase();
    if (closing) {
      for (var i = stack.length - 1; i > 0; i--) {
        if (stack[i].tagName === tag.toUpperCase()) { stack.length = i; break; }
      }
      continue;
    }
    var el = makeElement(tag);
    _parseAttrs(el, m[3]);
    stack[stack.length - 1].appendChild(el);
    if (m[4] !== '/' && !VOID_TAGS[tag]) stack.push(el);
  }
  pushText(html.slice(last));
  return root;
}

// Splits a rendered templates partial into <template> elements on the host.
function installTemplates(doc, html) {
  var host = doc.body || doc._body || doc._root;
  var re = /<template id="([^"]+)"[^>]*>([\s\S]*?)<\/template>/g;
  var m;
  var installed = [];
  while ((m = re.exec(html)) !== null) {
    var tpl = makeElement('template');
    tpl.id = m[1];
    var content = makeElement('div');
    var parsed = parseHtmlTree(m[2]);
    while (parsed.children.length) content.appendChild(parsed.children[0]);
    tpl.content = content;
    host.appendChild(tpl);
    installed.push(m[1]);
  }
  return installed;
}

function createMockDocument() {
  var body = makeElement('body');
  var doc = {
    _body: body,
    documentElement: body,
    createElement: function (tag) { return makeElement(tag); },
    createTextNode: function (text) {
      var node = makeElement('span');
      node.isText = true;
      node.textContent = text;
      return node;
    },
    getElementById: function (id) {
      return doc.querySelector('#' + id);
    },
    querySelector: function (sel) { return querySelectorAll(body, sel)[0] || null; },
    querySelectorAll: function (sel) { return querySelectorAll(body, sel); },
    addEventListener: function () {},
    body: body,
  };
  doc.body.tagName = 'BODY';
  return doc;
}

// ── Mock FormData ──

function createMockFormData() {
  return function (form) {
    this._fields = form ? form._fields || {} : {};
    this.append = function (k, v) { this._fields[k] = v; };
    this.get = function (k) { return this._fields[k]; };
    this[Symbol.iterator] = function () {
      return Object.entries(this._fields)[Symbol.iterator]();
    };
  };
}

// ── Mock form helper (used by extractData tests) ──

function createMockForm(fields, queryMap) {
  return {
    _fields: fields,
    querySelector: function (sel) {
      if (queryMap && queryMap[sel] !== undefined) {
        return { value: queryMap[sel] };
      }
      if (sel.indexOf('name="type"') >= 0) {
        return { value: fields.type || '' };
      }
      if (sel.indexOf('name="or_no_fallbacks"') >= 0) {
        return { value: 'true' };
      }
      if (sel.indexOf('name="') >= 0) {
        var m = sel.match(/name="([^"]+)"/);
        if (m) {
          var name = m[1];
          var raw = fields[name] !== undefined ? String(fields[name]) : '';
          var entry = { value: raw };
          if (name === 'retry_enabled') {
            entry.value = fields[name] !== undefined ? raw : 'true';
          } else if (name === 'retry_rate_limit') {
            entry.checked = fields[name] !== undefined ? raw !== 'false' : false;
          } else if (name === 'retry_server_error' || name === 'retry_timeout') {
            entry.checked = raw !== 'false';
          }
          return entry;
        }
      }
      return null;
    },
  };
}

// ── Mock IntersectionObserver ──

function createMockIntersectionObserver() {
  var instances = [];
  var Ctor = function (callback) {
    this._callback = callback;
    this._elements = [];
    instances.push(this);
  };
  Ctor.prototype.observe = function (el) { this._elements.push(el); };
  Ctor.prototype.unobserve = function () {};
  Ctor.prototype.disconnect = function () {};
  Ctor.prototype._trigger = function (entries) {
    this._callback(entries);
  };
  Ctor._instances = instances;
  return Ctor;
}

// ── Mock AbortController ──

function createMockAbortController() {
  var signal = { aborted: false, addEventListener: function () {} };
  var Ctor = function () {
    this.signal = signal;
    this.abort = function () { signal.aborted = true; };
  };
  return Ctor;
}

// ── Test harness ──

function printSummary() {
  // Defer past the pending microtasks so assertions inside promise chains are
  // counted, and let already-scheduled timers run before the exit.
  setTimeout(function () {
    console.log('\n' + tests + ' tests, ' + failures + ' failures');
    process.exit(failures > 0 ? 1 : 0);
  }, 0);
}

// Module tests assert the request a call site builds (URL, method, body)
// synchronously. `hxJson`/`hxFetch` in hx-queue.js defer through the serializer,
// which is covered by test-hx-queue.js on its own, so these wrappers call fetch
// directly and keep the module tests deterministic.
function jsonOpts(method, body) {
  var opts = { method: method || 'POST', headers: {} };
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json';
    opts.body = JSON.stringify(body);
  }
  return opts;
}

function installRequestPrimitives(globalObj) {
  globalObj.jsonOpts = jsonOpts;
  globalObj.hxJson = function (url, method, body) {
    return globalObj.fetch(url, jsonOpts(method, body));
  };
  globalObj.hxFetch = function (url, opts) {
    return globalObj.fetch(url, opts);
  };
  globalObj.hxGet = function (url, opts) {
    return globalObj.htmx.ajax('GET', url, opts);
  };
  globalObj.hxPost = function (url, opts) {
    return globalObj.htmx.ajax('POST', url, opts);
  };
}

function resetGlobals(globalObj) {
  if (globalObj._dispatchedEvents) globalObj._dispatchedEvents = [];
  if (globalObj._lastFetch) globalObj._lastFetch = null;
}

// ── Setup standard browser globals on `globalObj` ──
// Returns an object with { document, localStorage, fetch, CustomEvent, FormData }

function setupBrowserGlobals(globalObj) {
  var doc = createMockDocument();
  var ls = createMockLocalStorage();
  var fetchFn = createMockFetch();

  globalObj.window = globalObj;
  globalObj.document = doc;
  globalObj.localStorage = ls;
  globalObj.fetch = fetchFn;
  globalObj.alert = function () {};
  globalObj.setTimeout = function (fn) { fn(); };
  globalObj.clearTimeout = function () {};
  globalObj.setInterval = function () { return 1; };
  globalObj.clearInterval = function () {};
  globalObj.requestAnimationFrame = function (fn) { fn(); };
  globalObj.Math = Math;
  globalObj.JSON = JSON;

  var CustomEventCtor = createMockCustomEvent();
  globalObj.CustomEvent = CustomEventCtor;
  globalObj._dispatchedEvents = CustomEventCtor._events;

  globalObj.dispatchEvent = function (ev) { globalObj._dispatchedEvents.push(ev); };

  return {
    document: doc,
    localStorage: ls,
    fetch: fetchFn,
    CustomEvent: CustomEventCtor,
    _dispatchedEvents: CustomEventCtor._events,
  };
}

module.exports = {
  assert: assert,
  assertEqual: assertEqual,
  assertDeepEqual: assertDeepEqual,
  assertIncludes: assertIncludes,
  assertNotIncludes: assertNotIncludes,
  makeElement: makeElement,
  matches: matches,
  querySelectorAll: querySelectorAll,
  createMockLocalStorage: createMockLocalStorage,
  createMockFetch: createMockFetch,
  createMockCustomEvent: createMockCustomEvent,
  createMockDocument: createMockDocument,
  createMockFormData: createMockFormData,
  createMockForm: createMockForm,
  createMockIntersectionObserver: createMockIntersectionObserver,
  createMockAbortController: createMockAbortController,
  parseHtmlTree: parseHtmlTree,
  installTemplates: installTemplates,
  setupBrowserGlobals: setupBrowserGlobals,
  resetGlobals: resetGlobals,
  installRequestPrimitives: installRequestPrimitives,
  jsonOpts: jsonOpts,
  printSummary: printSummary,
  failures: failures,
  tests: tests,
};
