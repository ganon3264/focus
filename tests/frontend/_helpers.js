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
    parent: null,
    setAttribute: function (k, v) { this._attrs[k] = v; },
    getAttribute: function (k) { return this._attrs[k]; },
    hasAttribute: function (k) { return k in this._attrs; },
    removeAttribute: function (k) { delete this._attrs[k]; },
    appendChild: function (c) {
      // If already a child, move to end (like real DOM)
      var idx = this.children.indexOf(c);
      if (idx >= 0) this.children.splice(idx, 1);
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
    insertBefore: function (newEl, refEl) {
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
  Object.defineProperty(el, 'firstElementChild', {
    get: function () { return el.children.length > 0 ? el.children[0] : null; },
  });
  Object.defineProperty(el, 'nextElementSibling', {
    get: function () {
      if (!el.parent) return null;
      var idx = el.parent.children.indexOf(el);
      if (idx >= 0 && idx + 1 < el.parent.children.length) return el.parent.children[idx + 1];
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

function _matchesSimple(el, sel) {
  if (sel[0] === '.' && !/[\[ :#]/.test(sel) && sel.indexOf('.', 1) === -1) return el.classList.contains(sel.slice(1));
  if (sel[0] === '#' && sel.indexOf('[') === -1 && sel.indexOf('.') === -1) return el.id === sel.slice(1);
  return null;
}

function matches(el, sel) {
  if (!el || !el.tagName) return false;
  if (sel === '*') return true;
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
  // Handle [attr="value"] selectors
  var attrRe = /\[(\w[\w-]*)\s*=\s*"([^"]*)"\]/;
  var attrMatch = attrRe.exec(sel);
  if (attrMatch) {
    var attrSel = attrMatch[0];
    var attrName = attrMatch[1];
    var attrVal = attrMatch[2];
    var baseSel = sel.slice(0, attrMatch.index) + sel.slice(attrMatch.index + attrSel.length);
    if (baseSel) {
      if (!matches(el, baseSel)) return false;
    }
    if (el.getAttribute(attrName) !== attrVal) return false;
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

function createMockDocument() {
  var body = makeElement('body');
  var doc = {
    _body: body,
    documentElement: body,
    createElement: function (tag) { return makeElement(tag); },
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
        if (m) return { value: fields[m[1]] !== undefined ? String(fields[m[1]]) : '' };
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
  console.log('\n' + tests + ' tests, ' + failures + ' failures');
  process.exit(failures > 0 ? 1 : 0);
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
  setupBrowserGlobals: setupBrowserGlobals,
  resetGlobals: resetGlobals,
  printSummary: printSummary,
  failures: failures,
  tests: tests,
};
