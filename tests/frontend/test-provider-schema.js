// Unit tests for ProviderSchema (static/js/core/provider-schema.js).
var h = require('./helpers.js');
var assert = h.assert, assertEqual = h.assertEqual, assertDeepEqual = h.assertDeepEqual;
var path = require('path');
var fs = require('fs');

global.window = global;
global.PROVIDER_SCHEMA = {
  baseDefaults: {
    temperature: 1.0, max_tokens: 8192, include_reasoning: false,
    seed: -1, verbosity: '', image_format: 'webp',
  },
  types: {
    openrouter: {
      defaults: { top_k: 0, preserve_thinking: 'tool_only' },
      forwardAlways: ['top_k', 'include_reasoning', 'seed', 'verbosity'],
      forwardReasoning: ['reasoning_effort', 'thinking_budget'],
      visible: ['top_k', 'include_reasoning', 'reasoning_effort'],
      effortOptions: [{ value: 'low', label: 'Low' }, { value: 'high', label: 'High' }],
      capabilities: { supports_ephemeral_cache: true, supports_prefill: true },
      form: { orFields: true, modelInput: true, baseUrl: false, vertexFields: false, modelRequired: true },
    },
    openai_compat: {
      defaults: { image_format: 'png' },
      forwardAlways: ['include_reasoning'],
      forwardReasoning: ['reasoning_effort'],
      effortOptions: [{ value: 'low', label: 'Low' }],
      capabilities: { supports_ephemeral_cache: false },
    },
  },
};

eval(fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'core', 'provider-schema.js'), 'utf8'));

// ── defaults ──
assertDeepEqual(
  ProviderSchema.getSamplerDefaults('openrouter'),
  { temperature: 1.0, max_tokens: 8192, include_reasoning: false, seed: -1, verbosity: '', image_format: 'webp', top_k: 0, preserve_thinking: 'tool_only' },
  'openrouter defaults = base + overrides',
);
assertEqual(ProviderSchema.getSamplerDefaults('openai_compat').image_format, 'png', 'type override wins over base');
assertEqual(ProviderSchema.getSamplerDefaults('unknown').include_reasoning, false, 'unknown type falls back to base defaults only');

// ── effort options ──
assertDeepEqual(ProviderSchema.getSamplerEffortOptions('openrouter').map(function (o) { return o.value; }), ['low', 'high'], 'openrouter effort options');
assertDeepEqual(ProviderSchema.getSamplerEffortOptions('unknown').map(function (o) { return o.value; }), ['low'], 'unknown falls back to openai_compat options');

// ── buildSamplers ──
assertDeepEqual(
  ProviderSchema.buildSamplers('openrouter', { top_k: 5, include_reasoning: false, seed: 42, verbosity: 'low', reasoning_effort: 'high' }),
  { top_k: 5, include_reasoning: false, seed: 42, verbosity: 'low' },
  'reasoning fields omitted when reasoning off; seed/verbosity kept when valid',
);
assertDeepEqual(
  ProviderSchema.buildSamplers('openrouter', { top_k: 5, include_reasoning: true, seed: -1, verbosity: '', reasoning_effort: 'high', thinking_budget: 100 }),
  { top_k: 5, include_reasoning: true, reasoning_effort: 'high', thinking_budget: 100 },
  'reasoning fields added; -1 seed and empty verbosity dropped',
);
assertDeepEqual(
  ProviderSchema.buildSamplers('openai_compat', { include_reasoning: true, reasoning_effort: 'medium', frequency_penalty: 1 }),
  { include_reasoning: true, reasoning_effort: 'medium' },
  'openai_compat forwards only its own fields',
);
assertDeepEqual(ProviderSchema.buildSamplers('unknown', { temperature: 1 }), {}, 'unknown type forwards nothing provider-specific');

// ── capabilities / fieldVisible ──
assertEqual(ProviderSchema.capabilities('openrouter').supports_ephemeral_cache, true, 'capabilities passthrough');
assertEqual(ProviderSchema.capabilities('openrouter').supports_prefill, true, 'capabilities passthrough 2');
assertEqual(ProviderSchema.fieldVisible('openrouter', 'top_k'), true, 'fieldVisible true when listed');
assertEqual(ProviderSchema.fieldVisible('openrouter', 'frequency_penalty'), false, 'fieldVisible false when absent');
assertEqual(ProviderSchema.fieldVisible('openrouter', 'anything'), false, 'fieldVisible defaults false');

// ── form config ──
assertEqual(ProviderSchema.formConfig('openrouter').orFields, true, 'form config passthrough');
assertEqual(ProviderSchema.formConfig('openrouter').baseUrl, false, 'form config passthrough 2');
assertEqual(ProviderSchema.formConfig('unknown').baseUrl, true, 'form config default for unknown type');
