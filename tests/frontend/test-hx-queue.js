// Tests for the serialized htmx request queue (hxQueue / hxGet / hxPost).

var h = require('./helpers.js');
var assert = h.assert;
var assertEqual = h.assertEqual;

global.window = global;

var calls = [];
var resolvers = [];
global.htmx = {
  ajax: function (method, url, opts) {
    calls.push({ method: method, url: url, opts: opts });
    return new Promise(function (resolve) { resolvers.push(resolve); });
  },
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

  h.printSummary();
}

main().catch(function (e) {
  console.error(e);
  process.exit(1);
});
