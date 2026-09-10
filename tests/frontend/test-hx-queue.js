// Tests for the serialized htmx request queue (hxQueue / hxGet / hxPost).

var h = require('./helpers.js');
var assert = h.assert;
var assertEqual = h.assertEqual;

global.window = global;

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

  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
