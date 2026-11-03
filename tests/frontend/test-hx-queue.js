// Tests for the serialized htmx request queue (hxQueue / hxGet / hxPost).

var h = require('./helpers.js');
var assert = h.assert;
var assertEqual = h.assertEqual;

global.window = global;

// Minimal DOM: hxGet/hxPost must issue from a dedicated source element that
// lives in the document (htmx drops a request whose source is detached).
var nodes = [];
var srcEl = null;
global.document = {
  body: {
    appendChild: function (el) {
      el.parentNode = global.document.body;
      nodes.push(el);
    },
  },
  createElement: function () {
    return {
      id: '',
      className: '',
      attrs: {},
      parentNode: null,
      getRootNode: function () {
        return this.parentNode ? global.document : this;
      },
      setAttribute: function (k, v) {
        this.attrs[k] = v;
      },
    };
  },
  getElementById: function (id) {
    if (srcEl && srcEl.id === id) return srcEl;
    for (var i = 0; i < nodes.length; i++) if (nodes[i].id === id) return nodes[i];
    return null;
  },
};

var calls = [];
var resolvers = [];
var fetchCalls = [];
var fetchResolvers = [];
global.htmx = {
  ajax: function (method, url, opts) {
    calls.push({ method: method, url: url, opts: opts });
    return new Promise(function (resolve) { resolvers.push(resolve); });
  },
};
global.fetch = function (url, opts) {
  fetchCalls.push({ url: url, opts: opts });
  return new Promise(function (resolve) { fetchResolvers.push(resolve); });
};

var fs = require('fs');
var path = require('path');
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'hx-queue.js'), 'utf8'));

function flush() {
  return new Promise(function (resolve) { setTimeout(resolve, 0); });
}

async function main() {
  // Two concurrent hxGet calls: only the first should reach htmx.ajax.
  var a = hxGet('/a', { target: '#a', swap: 'innerHTML' });
  var b = hxGet('/b', { target: '#b', swap: 'innerHTML' });

  await flush();
  assertEqual(calls.length, 1, 'second hxGet is queued behind first');
  assertEqual(calls[0].url, '/a', 'first request issued first');

  resolvers.shift()();
  await flush();
  assertEqual(calls.length, 2, 'second hxGet runs after first resolves');
  assertEqual(calls[1].url, '/b', 'second request issued second');

  resolvers.shift()();
  await Promise.all([a, b]);

  // A rejected task must not break the chain.
  calls.length = 0;
  resolvers.length = 0;
  var failing = hxQueue(function () { return Promise.reject('boom'); });
  var next = hxGet('/c', { target: '#c', swap: 'innerHTML' });

  await failing.catch(function () {});
  await flush();
  assertEqual(calls.length, 1, 'request after a rejected task still runs');
  assertEqual(calls[0].url, '/c', 'rejected task did not poison the queue');

  resolvers.shift()();
  await next;

  // hxFetch shares the same serializer as hxGet/hxPost.
  fetchCalls.length = 0;
  fetchResolvers.length = 0;
  var f1 = hxFetch('/f1');
  var f2 = hxFetch('/f2');
  await flush();
  assertEqual(fetchCalls.length, 1, 'second hxFetch is queued behind the first');
  assertEqual(fetchCalls[0].url, '/f1', 'first fetch issued first');
  fetchResolvers.shift()({ ok: true });
  await flush();
  assertEqual(fetchCalls.length, 2, 'second hxFetch runs after the first resolves');
  fetchResolvers.shift()({ ok: true });
  await Promise.all([f1, f2]);

  // And it orders against htmx requests too.
  calls.length = 0;
  resolvers.length = 0;
  fetchCalls.length = 0;
  fetchResolvers.length = 0;
  var f3 = hxFetch('/f3');
  var g = hxGet('/g', {});
  await flush();
  assertEqual(fetchCalls.length, 1, 'fetch issued before a queued hxGet');
  assertEqual(calls.length, 0, 'hxGet waits for the fetch');
  fetchResolvers.shift()({ ok: true });
  await flush();
  assertEqual(calls.length, 1, 'hxGet runs once the fetch resolves');
  resolvers.shift()();
  await Promise.all([f3, g]);

  // ── Programmatic requests carry their own htmx source ──
  // htmx queues per source element and drops on conflict, so a shared
  // document.body source silently swallowed reloads. Every hxGet/hxPost must
  // issue from the dedicated `hx-source` element, which queues instead.
  calls.length = 0;
  resolvers.length = 0;
  srcEl = null;
  nodes.length = 0;
  var s1 = hxGet('/s1', { target: '#s1', swap: 'innerHTML' });
  await flush();
  assert(calls[0].opts.source != null, 'hxGet passes an htmx source element');
  assertEqual(calls[0].opts.source.attrs['hx-sync'], 'this:queue all', 'source queues instead of dropping');
  assertEqual(calls[0].opts.source.parentNode, document.body, 'source lives in the document');
  assertEqual(calls[0].opts.target, '#s1', 'caller target survives');
  resolvers.shift()();
  await s1;

  var s2 = hxGet('/s2', {});
  await flush();
  assertEqual(
    calls[calls.length - 1].opts.source,
    calls[0].opts.source,
    'all requests share the one queue source',
  );
  resolvers.shift()();
  await s2;

  var stringTarget = hxPost('/s3', '#s3');
  await flush();
  assertEqual(calls[calls.length - 1].opts.target, '#s3', 'a bare string opts is a target');
  assert(calls[calls.length - 1].opts.source != null, 'bare string opts still gets a source');
  resolvers.shift()();
  await stringTarget;

  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
