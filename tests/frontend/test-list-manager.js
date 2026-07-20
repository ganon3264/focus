// Unit tests for list-manager.js — config-driven card grid manager
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;
var makeElement = h.makeElement;

var path = require('path');
var fs = require('fs');

var storage = {};
global.localStorage = {
  getItem: function (k) { return storage.hasOwnProperty(k) ? storage[k] : null; },
  setItem: function (k, v) { storage[k] = String(v); },
  removeItem: function (k) { delete storage[k]; },
};
global.window = global;
global.fetch = function () { return Promise.resolve({ ok: true }); };
global.document = h.createMockDocument();
global.alert = function () {};
global.htmx = { ajax: function () {} };
global.customConfirm = function (html, cb) { cb(true); };
global.setTimeout = function (fn) { fn(); };

// Load module
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'ui', 'list-manager.js'), 'utf8'));

assert(!!window.ListManager, 'ListManager loaded');

// Build a grid with cards
var grid = makeElement('div');
grid.style = {};
grid.id = 'test-grid';

function addCard(name, created) {
  var card = makeElement('div');
  card.style = {};
  card.classList.add('card');
  card.setAttribute('data-name', name);
  card.setAttribute('data-created', created);
  var full = makeElement('div');
  full.style = {};
  full.classList.add('card-full');
  var compact = makeElement('div');
  compact.style = {};
  compact.classList.add('card-compact');
  card.appendChild(full);
  card.appendChild(compact);
  grid.appendChild(card);
  return card;
}
var cardA = addCard('Alpha', '2024-01-03');
var cardB = addCard('Beta', '2024-01-01');
var cardC = addCard('Gamma', '2024-01-02');

global.document._body.appendChild(grid);
global.document.getElementById = function (id) {
  if (id === 'test-grid') return grid;
  if (id === 'sort-select') return makeElement('select');
  if (id === 'new-item-input') return makeElement('input');
  return null;
};
// Override querySelectorAll to handle #grid .card descendant selectors
var _origQSA = global.document.querySelectorAll;
global.document.querySelectorAll = function (sel) {
  if (sel.indexOf(' ') >= 0) {
    var parts = sel.split(/\s+/);
    var ancestors = _origQSA(parts[0]);
    var result = [];
    for (var a = 0; a < ancestors.length; a++) {
      var subs = h.querySelectorAll(ancestors[a], parts.slice(1).join(' '));
      for (var s = 0; s < subs.length; s++) result.push(subs[s]);
    }
    return result;
  }
  return _origQSA(sel);
};

var cfg = {
  gridId: 'test-grid',
  dataNameAttr: 'data-name',
  dataCreatedAttr: 'data-created',
  filterFn: 'filterTest',
  sortFn: 'sortTest',
  applyCompactFn: 'applyCompactTest',
  toggleCompactFn: 'toggleCompactTest',
  newItemFn: 'newItemTest',
  newItemLabel: 'New Item',
  newItemInputId: 'new-item-input',
  sortStorageKey: 'sort_test',
  viewStorageKey: 'view_test',
  sortSelectId: 'sort-select',
  viewFullClass: 'card-full',
  viewCompactClass: 'card-compact',
  apiEndpoint: '/api/test-items',
  hxRoute: '/partials/test-items',
  hxTarget: '#test-grid',
};

// Setup restores view/sort
window.ListManager.setup(cfg);

// ── filterFn filters by name (case-sensitive, query lowercased) ──
(function () {
  // 'eta' matches 'Beta' (case-sensitive match at index 1)
  window.filterTest('eta');
  assertEqual(cardA.style.display, 'none', 'filter hides Alpha (no match)');
  assertEqual(cardB.style.display, '', 'filter shows Beta (matches "eta")');
  assertEqual(cardC.style.display, 'none', 'filter hides Gamma (no match)');
  // Reset
  window.filterTest('');
  assertEqual(cardA.style.display, '', 'filter reset shows all');
  assertEqual(cardB.style.display, '', 'filter reset shows all');
  assertEqual(cardC.style.display, '', 'filter reset shows all');
})();

// ── sortFn sorts az ──
(function () {
  window.sortTest('az');
  var cards = grid.querySelectorAll('.card');
  assertEqual(cards[0].getAttribute('data-name'), 'Alpha', 'sort az: first is Alpha');
  assertEqual(cards[1].getAttribute('data-name'), 'Beta', 'sort az: second is Beta');
  assertEqual(cards[2].getAttribute('data-name'), 'Gamma', 'sort az: third is Gamma');
})();

// ── sortFn sorts za ──
(function () {
  window.sortTest('za');
  var cards = grid.querySelectorAll('.card');
  var names = [];
  for (var i = 0; i < cards.length; i++) names.push(cards[i].getAttribute('data-name'));
  assertEqual(names[0], 'Gamma', 'sort za: first is Gamma');
})();

// ── sortFn sorts newest ──
(function () {
  window.sortTest('newest');
  var cards = grid.querySelectorAll('.card');
  var names = [];
  for (var i = 0; i < cards.length; i++) names.push(cards[i].getAttribute('data-name'));
  assertEqual(names[0], 'Alpha', 'sort newest: first is Alpha');
})();

// ── sortFn sorts oldest ──
(function () {
  window.sortTest('oldest');
  var cards = grid.querySelectorAll('.card');
  var names = [];
  for (var i = 0; i < cards.length; i++) names.push(cards[i].getAttribute('data-name'));
  assertEqual(names[0], 'Beta', 'sort oldest: first is Beta');
})();

// ── applyCompactFn toggles view ──
(function () {
  window.applyCompactTest(true);
  assertEqual(grid.dataset.view, 'compact', 'compact view set');
  assert(
    grid.querySelectorAll('.card-full')[0].style.display === 'none',
    'compact hides .card-full',
  );
  assert(
    grid.querySelectorAll('.card-compact')[0].style.display === 'block',
    'compact shows .card-compact',
  );

  window.applyCompactTest(false);
  assertEqual(grid.dataset.view, 'full', 'full view set');
})();

// ── toggleCompactFn toggles compact ──
(function () {
  grid.dataset.view = 'full';
  window.toggleCompactTest();
  assertEqual(grid.dataset.view, 'compact', 'toggleCompact switches to compact');
  window.toggleCompactTest();
  assertEqual(grid.dataset.view, 'full', 'toggleCompact switches back to full');
})();

// ── Result ──
h.printSummary();
