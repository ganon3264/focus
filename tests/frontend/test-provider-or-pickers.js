// Regression: the OpenRouter route/quant/service-tier pickers must dispatch a
// `change` event on their hidden input. modal.js recomputes dirty state on
// `option-selected`, which fires *before* the picker callback updates the
// value, so the explicit change dispatch is what actually marks the modal dirty.
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual;

var path = require('path');
var fs = require('fs');

function makeEl(id) {
  return {
    id: id,
    value: '',
    textContent: '',
    _events: [],
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
    dispatchEvent: function (e) { this._events.push(e.type); return true; },
  };
}

var ids = [
  'prov-form-or-route', 'or-route-display-prov-form',
  'prov-form-or-quant', 'or-quant-display-prov-form',
  'prov-form-or-service-tier', 'or-service-tier-display-prov-form',
];
var els = {};
ids.forEach(function (id) { els[id] = makeEl(id); });

global.window = global;
global.document = {
  body: { addEventListener: function () {} },
  getElementById: function (id) { return els[id] || null; },
  querySelector: function () { return null; },
  querySelectorAll: function () { return []; },
  addEventListener: function () {},
};
global.alert = function () {};
global.StateManager = { get: function () { return null; } };
global.api = {};
global.FormData = h.createMockFormData();
global.openModal = function () {};
global.closeModal = function () {};

var captured = null;
global.openOptionPicker = function (options, title, cb) {
  captured = { options: options, title: title, cb: cb };
};

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'providers.js'), 'utf8'));

(function () {
  openRouteSelectModal('prov-form');
  captured.cb('ProvA', 'ProvA');
  assertEqual(els['prov-form-or-route'].value, 'ProvA', 'route: hidden input set');
  assert(els['prov-form-or-route']._events.indexOf('change') >= 0, 'route: change dispatched for dirty tracking');
})();

(function () {
  openQuantSelectModal('prov-form');
  captured.cb('fp16', 'fp16');
  assertEqual(els['prov-form-or-quant'].value, 'fp16', 'quant: hidden input set');
  assert(els['prov-form-or-quant']._events.indexOf('change') >= 0, 'quant: change dispatched for dirty tracking');
})();

(function () {
  openServiceTierSelectModal('prov-form');
  captured.cb('flex', 'Flex (cheaper, slower)');
  assertEqual(els['prov-form-or-service-tier'].value, 'flex', 'service tier: hidden input set');
  assertEqual(els['or-service-tier-display-prov-form'].textContent, 'Flex (cheaper, slower)', 'service tier: label set');
  assert(els['prov-form-or-service-tier']._events.indexOf('change') >= 0, 'service tier: change dispatched for dirty tracking');
})();

h.printSummary();
