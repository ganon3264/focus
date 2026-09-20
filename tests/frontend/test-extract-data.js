// Unit tests for extractData() in providers.js
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;
var createMockForm = h.createMockForm;

var path = require('path');
var fs = require('fs');

// Mock FormData
var MockFormData = h.createMockFormData();
global.FormData = MockFormData;

// Mock window globals needed by providers.js
global.window = global;
global.alert = function () {};
global.StateManager = { get: function () { return null; } };
global.api = {};
global.htmx = { ajax: function () { return Promise.resolve(); } };
global.openModal = function () {};
global.closeModal = function () {};

var DEFAULT_RETRY = {
  enabled: true,
  max_retries: 5,
  base_delay: 2,
  max_delay: 20,
  on_rate_limit: false,
  on_server_error: true,
  on_timeout: true,
  extra_statuses: [],
};

// Load module
eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'modals', 'providers.js'), 'utf8'));

// ── openai_compat — basic fields ──
(function () {
  var form = createMockForm({
    name: 'My Provider',
    type: 'openai_compat',
    base_url: 'http://localhost:8080/v1',
    api_key: 'sk-test-123',
    model: 'gpt-4',
    params: '{"temperature":0.7}',
  });
  var data = extractData(form);
  assertEqual(data.name, 'My Provider', 'openai_compat: name preserved');
  assertEqual(data.type, 'openai_compat', 'openai_compat: type preserved');
  assertEqual(data.base_url, 'http://localhost:8080/v1', 'openai_compat: base_url preserved');
  assertEqual(data.api_key, 'sk-test-123', 'openai_compat: api_key preserved');
  assertEqual(data.model, 'gpt-4', 'openai_compat: model preserved');
  assertDeepEqual(data.params, { temperature: 0.7, retry: DEFAULT_RETRY }, 'openai_compat: params parsed');
  assert(!data.or_model, 'openai_compat: or_model absent');
  assert(!data.or_route, 'openai_compat: or_route deleted');
})();

// ── openai_compat — hidden api_key removed ──
(function () {
  var form = createMockForm({ name: 'P', type: 'openai_compat', model: 'gpt-4', api_key: '__HIDDEN__' });
  var data = extractData(form);
  assert(!data.api_key, 'openai_compat: __HIDDEN__ api_key removed');
})();

// ── openrouter — full config ──
(function () {
  var form = createMockForm({
    name: 'OR',
    type: 'openrouter',
    model: 'anthropic/claude-3',
    or_route: 'fallback',
    or_quant: 'fp16',
    params: '{}',
  });
  var data = extractData(form);
  assertEqual(data.model, 'anthropic/claude-3', 'openrouter: model preserved');
  assertEqual(data.base_url, 'https://openrouter.ai/api/v1', 'openrouter: base_url set');
  assertEqual(data.params.or_route, 'fallback', 'openrouter: or_route in params');
  assertEqual(data.params.or_quant, 'fp16', 'openrouter: or_quant in params');
  assert(!data.or_route, 'openrouter: or_route deleted');
  assert(!data.or_quant, 'openrouter: or_quant deleted');
})();

// ── openrouter — no route/quant ──
(function () {
  var form = createMockForm({
    name: 'OR Simple',
    type: 'openrouter',
    model: 'openai/gpt-4o',
    or_route: '',
    or_quant: '',
    params: '{}',
  });
  var data = extractData(form);
  assertEqual(data.model, 'openai/gpt-4o', 'openrouter simple: model set');
  assert(!data.params.or_route, 'openrouter simple: no or_route in params');
  assert(!data.params.or_quant, 'openrouter simple: no or_quant in params');
})();

// ── openrouter — no model shows error toast ──
(function () {
  var form = createMockForm({ name: 'Bad OR', type: 'openrouter', model: '' });
  var toasted = null;
  global.showErrorToast = function (msg) { toasted = msg; };
  var threw = false;
  try { extractData(form); } catch (e) { threw = true; }
  assert(toasted === 'Please select an OpenRouter model.', 'openrouter: no model triggers error toast');
  assert(threw, 'openrouter: no model throws');
  delete global.showErrorToast;
})();

// ── openrouter — invalid params json ──
(function () {
  var form = createMockForm({
    name: 'OR',
    type: 'openrouter',
    model: 'model',
    params: 'not-json',
  });
  var data = extractData(form);
  assertEqual(data.params.or_no_fallbacks, true, 'openrouter: or_no_fallbacks still set');
  assert(!data.params.or_route, 'openrouter: no or_route on invalid params');
})();

// ── google_vertex ──
(function () {
  var form = createMockForm({
    name: 'Vertex',
    type: 'google_vertex',
    model: 'gemini-2.0',
    vertex_region: 'us-central1',
    vertex_project_id: 'my-project',
    params: '{}',
  });
  var data = extractData(form);
  assertEqual(data.model, 'gemini-2.0', 'vertex: model preserved');
  assertEqual(data.base_url, '', 'vertex: base_url empty');
  assertEqual(data.params.vertex_region, 'us-central1', 'vertex: region in params');
  assertEqual(data.params.vertex_project_id, 'my-project', 'vertex: project_id in params');
  assert(!data.vertex_region, 'vertex: vertex_region deleted from top level');
  assert(!data.vertex_project_id, 'vertex: vertex_project_id deleted from top level');
})();

// ── google_aistudio ──
(function () {
  var form = createMockForm({
    name: 'AI Studio',
    type: 'google_aistudio',
    model: 'gemini-2.0-flash',
    api_key: 'sk-ai',
    params: '{"foo":"bar"}',
  });
  var data = extractData(form);
  assertEqual(data.model, 'gemini-2.0-flash', 'aistudio: model preserved');
  assert(!data.base_url, 'aistudio: base_url omitted');
  assertEqual(data.api_key, 'sk-ai', 'aistudio: api_key preserved');
  assertDeepEqual(data.params, { foo: 'bar', retry: DEFAULT_RETRY }, 'aistudio: params parsed');
})();

// ── retry config parsed from form ──
(function () {
  var form = createMockForm({
    name: 'R', type: 'openai_compat', model: 'm', params: '{}',
    retry_enabled: 'true',
    retry_max_retries: '5',
    retry_base_delay: '1.5',
    retry_max_delay: '45',
    retry_rate_limit: 'false',
    retry_server_error: 'true',
    retry_timeout: 'false',
    retry_extra_statuses: '408, 425, nope, 999',
  });
  var data = extractData(form);
  assertDeepEqual(data.params.retry, {
    enabled: true,
    max_retries: 5,
    base_delay: 1.5,
    max_delay: 45,
    on_rate_limit: false,
    on_server_error: true,
    on_timeout: false,
    extra_statuses: [408, 425],
  }, 'retry: config parsed from form');
  assert(!data.retry_enabled && !data.retry_extra_statuses, 'retry: form fields removed from top level');
})();

// ── retry disabled ──
(function () {
  var form = createMockForm({ name: 'R', type: 'openai_compat', model: 'm', params: '{}', retry_enabled: 'false' });
  var data = extractData(form);
  assertEqual(data.params.retry.enabled, false, 'retry: disabled flag preserved');
})();

// ── deepseek ──
(function () {
  var form = createMockForm({ name: 'DS', type: 'deepseek', model: 'deepseek-chat', params: '{}' });
  var data = extractData(form);
  assertEqual(data.model, 'deepseek-chat', 'deepseek: model preserved');
  assert(!data.base_url, 'deepseek: base_url omitted');
})();

// ── multi-key list → params.api_keys, first key mirrored to api_key ──
(function () {
  var form = createMockForm({
    name: 'P', type: 'openai_compat', model: 'gpt-4',
    api_keys_json: JSON.stringify(['SECRET:a', 'SECRET:b']),
  });
  var data = extractData(form);
  assertDeepEqual(data.params.api_keys, ['SECRET:a', 'SECRET:b'], 'api_keys parsed into params');
  assertEqual(data.api_key, 'SECRET:a', 'first key mirrored into api_key');
  assert(!data.api_keys_json, 'api_keys_json removed from the request body');
})();

// ── no key list → params.api_keys absent (legacy single key untouched) ──
(function () {
  var form = createMockForm({ name: 'P', type: 'openai_compat', model: 'gpt-4', api_key: 'sk-x' });
  var data = extractData(form);
  assert(!data.params.api_keys, 'absent api_keys_json leaves params.api_keys unset');
  assertEqual(data.api_key, 'sk-x', 'legacy api_key preserved');
})();

// ── malformed key list is ignored ──
(function () {
  var form = createMockForm({ name: 'P', type: 'openai_compat', model: 'gpt-4', api_keys_json: 'not json' });
  var data = extractData(form);
  assert(!data.params.api_keys, 'malformed api_keys_json is dropped');
})();

// ── Result ──
h.printSummary();
