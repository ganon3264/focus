window.PROVIDER_SAMPLERS = {
  openai_compat: {
    defaults: { preserve_thinking: "tool_only", image_format: "png" },
    build(s) {
      return {
        frequency_penalty: s.frequency_penalty,
        presence_penalty: s.presence_penalty,
        include_reasoning: s.include_reasoning,
        ...(s.include_reasoning ? {
          reasoning_effort: s.reasoning_effort,
          preserve_thinking: s.preserve_thinking,
        } : {}),
      };
    },
  },
  deepseek: {
    defaults: { preserve_thinking: "tool_only" },
    build(s) {
      return {
        include_reasoning: s.include_reasoning,
        ...(s.include_reasoning ? { preserve_thinking: s.preserve_thinking } : {}),
      };
    },
  },
  moonshot: {
    defaults: { preserve_thinking: "tool_only" },
    build(s) {
      return {
        frequency_penalty: s.frequency_penalty,
        presence_penalty: s.presence_penalty,
        include_reasoning: s.include_reasoning,
        ...(s.include_reasoning ? { preserve_thinking: s.preserve_thinking, reasoning_effort: s.reasoning_effort } : {}),
      };
    },
  },
  openrouter: {
    defaults: { top_k: 0, min_p: 0, repetition_penalty: 1.0, preserve_thinking: "tool_only" },
    build(s) {
      const p = {
        top_k: s.top_k,
        min_p: s.min_p,
        repetition_penalty: s.repetition_penalty,
        include_reasoning: s.include_reasoning,
        preserve_thinking: s.preserve_thinking,
        top_a: s.top_a,
        ...(s.seed >= 0 ? { seed: s.seed } : {}),
        verbosity: s.verbosity || undefined,
      };
      if (s.include_reasoning) {
        p.reasoning_effort = s.reasoning_effort;
        p.thinking_budget = s.thinking_budget;
      }
      p.cache_enabled = s.cache_enabled;
      p.cache_ttl = s.cache_ttl;
      p.cache_depth = s.cache_depth;
      return p;
    },
  },
  google_vertex: {
    defaults: {},
    build(s) {
      return {
        top_k: s.top_k,
        send_reasoning_history: s.send_reasoning_history,
        include_reasoning: s.include_reasoning,
        ...(s.include_reasoning ? { reasoning_effort: s.reasoning_effort } : {}),
      };
    },
  },
  google_aistudio: {
    defaults: {},
    build(s) {
      return {
        top_k: s.top_k,
        send_reasoning_history: s.send_reasoning_history,
        include_reasoning: s.include_reasoning,
        ...(s.include_reasoning ? { reasoning_effort: s.reasoning_effort } : {}),
      };
    },
  },
};

window.EFFORT_OPTIONS = {
  openrouter: [
    { value: 'minimal', label: 'Minimal' },
    { value: 'low', label: 'Low' },
    { value: 'medium', label: 'Medium' },
    { value: 'high', label: 'High' },
    { value: 'xhigh', label: 'X-High' },
    { value: 'max', label: 'Max' },
  ],
  openai_compat: [
    { value: 'low', label: 'Low' },
    { value: 'medium', label: 'Medium' },
    { value: 'high', label: 'High' },
  ],
  deepseek: [
    { value: 'high', label: 'High' },
    { value: 'max', label: 'Max' },
  ],
  moonshot: [
    { value: 'low', label: 'Low' },
    { value: 'high', label: 'High' },
    { value: 'max', label: 'Max' },
  ],
  google_vertex: [
    { value: 'MINIMAL', label: 'Min' },
    { value: 'LOW', label: 'Low' },
    { value: 'MEDIUM', label: 'Med' },
    { value: 'HIGH', label: 'High' },
  ],
  google_aistudio: [
    { value: 'MINIMAL', label: 'Min' },
    { value: 'LOW', label: 'Low' },
    { value: 'MEDIUM', label: 'Med' },
    { value: 'HIGH', label: 'High' },
  ],
};

window.BASE_SAMPLER_DEFAULTS = {
  temperature: 1.0,
  max_tokens: 8192,
  top_p: 0.95,
  top_k: 0,
  min_p: 0,
  frequency_penalty: 0.0,
  presence_penalty: 0.0,
  repetition_penalty: 1.0,
  include_reasoning: false,
  send_reasoning_history: true,
  reasoning_effort: 'max',
  thinking_budget: 0,
  stream_enabled: true,
  enable_multimodal: true,
  image_format: 'webp',
  cache_enabled: false,
  cache_ttl: 'ephemeral',
  cache_depth: 5,
  top_a: 0,
  seed: -1,
  verbosity: '',
};

window.getSamplerDefaults = function (providerType) {
  const provider = PROVIDER_SAMPLERS[providerType];
  return { ...BASE_SAMPLER_DEFAULTS, ...provider?.defaults };
};

window.getSamplerEffortOptions = function (providerType) {
  return EFFORT_OPTIONS[providerType] || EFFORT_OPTIONS.openai_compat;
};
