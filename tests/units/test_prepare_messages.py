"""Characterization tests for ``prepare_generation_messages``.

These tests deliberately pin the *current* observable behavior of the
request-preprocessing pipeline (messages mutated in place, gen_kwargs
produced) across every provider type and model-specific branch. They are the
safety net for the quirks refactor: Phases 2-3 must keep these green before
any behavior change lands.

The provider's modality lookup is stubbed via ``_patch_modalities``; everything
else is pure in-memory.
"""

import pytest

from focus.core.models import StreamRequest
from focus.providers import (
    DeepseekProvider,
    MoonshotProvider,
    OpenAICompatProvider,
    OpenRouterProvider,
    XiaomiMiMoProvider,
)
from focus.providers.google_base import GoogleProviderBase
from focus.routers.stream_utils import prepare_generation_messages


class _Provider:
    """Minimal stand-in for a provider instance. The pipeline reads
    ``supports_prefill`` and ``supported_modalities``."""

    def __init__(self, supports_prefill: bool = True, modalities: list[str] | None = None):
        self.supports_prefill = supports_prefill
        self._modalities = modalities

    async def supported_modalities(self, model: str) -> list[str] | None:
        return self._modalities


def _body(**kw) -> StreamRequest:
    return StreamRequest(chat_id="chat-1", **kw)


def _prov(ptype: str, model: str = "test-model") -> dict:
    return {"type": ptype, "model": model}


def _patch_modalities(monkeypatch, mods):
    async def fake(self, model):
        return mods

    monkeypatch.setattr(_Provider, "supported_modalities", fake)


@pytest.fixture(autouse=True)
def _no_openrouter_network(monkeypatch):
    """Every test runs offline; individual tests override the return value."""
    _patch_modalities(monkeypatch, None)


class TestCapabilityFlags:
    def test_openai_compat_defaults(self):
        assert OpenAICompatProvider.supports_prefill is True
        assert OpenAICompatProvider.echoes_prefill is True
        assert OpenAICompatProvider.supports_tools is True

    def test_deepseek_and_moonshot_do_not_echo_prefill(self):
        assert DeepseekProvider.echoes_prefill is False
        assert MoonshotProvider.echoes_prefill is False
        # ...but they still accept a prefill.
        assert DeepseekProvider.supports_prefill is True
        assert MoonshotProvider.supports_prefill is True

    def test_xiaomi_mimo_does_not_echo_prefill(self):
        assert XiaomiMiMoProvider.echoes_prefill is False
        assert XiaomiMiMoProvider.supports_prefill is True

    def test_google_does_not_support_prefill(self):
        assert GoogleProviderBase.supports_prefill is False
        assert GoogleProviderBase.supports_tools is True

    def test_openrouter_inherits_openai_compat_defaults(self):
        assert OpenRouterProvider.supports_prefill is True
        assert OpenRouterProvider.echoes_prefill is True


class TestSamplerForwarding:
    async def test_basic_samplers_forwarded(self):
        msgs = [{"role": "user", "content": "hi"}]
        _, kw = await prepare_generation_messages(
            _prov("openai_compat"), _body(samplers={"temperature": 0.7, "max_tokens": 256}),
            msgs, _Provider(), "chat-1",
        )
        assert kw["temperature"] == 0.7
        assert kw["max_tokens"] == 256

    async def test_internal_sampler_keys_stripped(self):
        msgs = [{"role": "user", "content": "hi"}]
        _, kw = await prepare_generation_messages(
            _prov("openai_compat"),
            _body(samplers={
                "temperature": 0.5,
                "disable_multimodal": False,
                "image_format": "webp",
                "cache_enabled": True,
                "cache_ttl": "1h",
                "cache_depth": 3,
            }),
            msgs, _Provider(), "chat-1",
        )
        assert kw == {"temperature": 0.5}

    async def test_empty_samplers_yield_empty_kwargs(self):
        _, kw = await prepare_generation_messages(
            _prov("openai_compat"), _body(), [{"role": "user", "content": "hi"}], _Provider(), "chat-1",
        )
        assert kw == {}

    async def test_stream_enabled_is_not_consumed_here(self):
        # Consumed later by stream.py; pinned so a refactor doesn't swallow it.
        _, kw = await prepare_generation_messages(
            _prov("openai_compat"), _body(samplers={"stream_enabled": False}),
            [{"role": "user", "content": "hi"}], _Provider(), "chat-1",
        )
        assert kw["stream_enabled"] is False


class TestModalityFiltering:
    async def test_disable_multimodal_strips_media(self):
        msgs = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": "data:,"}},
            ],
        }]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"), _body(samplers={"disable_multimodal": True}),
            msgs, _Provider(), "chat-1",
        )
        assert out[0]["content"] == "look"

    async def test_openrouter_model_modalities_strip_media(self, monkeypatch):
        _patch_modalities(monkeypatch, ["text"])
        msgs = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": "data:,"}},
            ],
        }]
        out, _ = await prepare_generation_messages(
            _prov("openrouter"), _body(), msgs, _Provider(), "chat-1",
        )
        assert out[0]["content"] == "look"

    async def test_openrouter_model_modalities_keep_supported_media(self, monkeypatch):
        _patch_modalities(monkeypatch, ["image"])
        msgs = [{
            "role": "user",
            "content": [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": "data:,"}},
            ],
        }]
        out, _ = await prepare_generation_messages(
            _prov("openrouter"), _body(), msgs, _Provider(), "chat-1",
        )
        assert isinstance(out[0]["content"], list)
        assert any(p.get("type") == "image_url" for p in out[0]["content"])

    async def test_openrouter_unknown_modalities_leave_messages_untouched(self, monkeypatch):
        _patch_modalities(monkeypatch, None)
        msgs = [{"role": "user", "content": "hi"}]
        out, _ = await prepare_generation_messages(
            _prov("openrouter"), _body(), msgs, _Provider(), "chat-1",
        )
        assert out[0]["content"] == "hi"


class TestClaudeCaching:
    async def test_cache_injected_for_claude_on_openrouter(self, monkeypatch):
        _patch_modalities(monkeypatch, None)
        msgs = [
            {"role": "system", "content": "sys", "_greeting": True},
            {"role": "user", "content": "hi"},
        ]
        out, kw = await prepare_generation_messages(
            _prov("openrouter", "anthropic/claude-3.5-sonnet"),
            _body(samplers={"cache_enabled": True, "cache_ttl": "1h", "cache_depth": 5}),
            msgs, _Provider(), "chat-1",
        )
        assert "cache_control" in out[0]["content"][0]
        assert out[0]["content"][0]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}
        assert "_greeting" not in out[0]
        assert "cache_enabled" not in kw
        assert "cache_ttl" not in kw
        assert "cache_depth" not in kw

    async def test_cache_skipped_for_non_claude_model(self, monkeypatch):
        _patch_modalities(monkeypatch, None)
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        out, _ = await prepare_generation_messages(
            _prov("openrouter", "openai/gpt-4o"),
            _body(samplers={"cache_enabled": True}),
            msgs, _Provider(), "chat-1",
        )
        assert isinstance(out[0]["content"], str)

    async def test_cache_skipped_for_non_openrouter(self):
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat", "anthropic/claude-3.5-sonnet"),
            _body(samplers={"cache_enabled": True}),
            msgs, _Provider(), "chat-1",
        )
        assert isinstance(out[0]["content"], str)


class TestGreetingAndReasoning:
    async def test_greeting_tag_removed_for_every_type(self):
        for ptype in ("openai_compat", "openrouter", "google_aistudio", "deepseek", "moonshot", "xiaomi_mimo"):
            msgs = [{"role": "assistant", "content": "hi", "_greeting": True}]
            out, _ = await prepare_generation_messages(
                _prov(ptype), _body(), msgs, _Provider(), "chat-1",
            )
            assert "_greeting" not in out[0], ptype

    async def test_thought_signature_stripped_for_non_google(self):
        msgs = [{"role": "assistant", "content": "a", "thought_signature": "sig"}]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"), _body(), msgs, _Provider(), "chat-1",
        )
        assert "thought_signature" not in out[0]

    async def test_thought_signature_kept_for_google(self):
        msgs = [{"role": "assistant", "content": "a", "thought_signature": "sig"}]
        out, _ = await prepare_generation_messages(
            _prov("google_aistudio"), _body(), msgs, _Provider(), "chat-1",
        )
        assert out[0]["thought_signature"] == "sig"

    async def test_foreign_reasoning_dropped_on_openrouter(self, monkeypatch):
        _patch_modalities(monkeypatch, None)
        msgs = [{
            "role": "assistant",
            "content": "a",
            "reasoning_details": [{"format": "anthropic-claude-v1", "text": "x"}],
            "_src_model": "anthropic/claude-3",
        }]
        out, _ = await prepare_generation_messages(
            # preserve_thinking=all so only the foreign-model logic can remove it
            _prov("openrouter", "openai/gpt-4o"), _body(samplers={"preserve_thinking": "all"}),
            msgs, _Provider(), "chat-1",
        )
        assert "_src_model" not in out[0]
        assert out[0].get("reasoning_details") is None

    async def test_same_model_reasoning_details_kept_on_openrouter(self, monkeypatch):
        _patch_modalities(monkeypatch, None)
        msgs = [{
            "role": "assistant",
            "content": "a",
            "reasoning_details": [{"format": "anthropic-claude-v1", "text": "x"}],
            "_src_model": "openai/gpt-4o",
        }]
        out, _ = await prepare_generation_messages(
            _prov("openrouter", "openai/gpt-4o"), _body(samplers={"preserve_thinking": "all"}),
            msgs, _Provider(), "chat-1",
        )
        assert out[0]["reasoning_details"][0]["format"] == "anthropic-claude-v1"

    async def test_src_model_popped_for_non_openrouter(self):
        msgs = [{"role": "user", "content": "hi", "_src_model": "whatever"}]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"), _body(), msgs, _Provider(), "chat-1",
        )
        assert "_src_model" not in out[0]

    async def test_reasoning_details_filtered_for_openai_compat(self):
        msgs = [{
            "role": "assistant",
            "content": "a",
            "reasoning_details": [
                {"format": "anthropic-claude-v1", "text": "drop"},
                {"format": "openai-responses-v1", "text": "keep"},
            ],
        }]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"),
            _body(samplers={"preserve_thinking": "all"}),
            msgs, _Provider(), "chat-1",
        )
        assert [i["format"] for i in out[0]["reasoning_details"]] == ["openai-responses-v1"]

    async def test_reasoning_details_untouched_for_openrouter(self, monkeypatch):
        _patch_modalities(monkeypatch, None)
        msgs = [{
            "role": "assistant",
            "content": "a",
            "reasoning_details": [{"format": "anthropic-claude-v1", "text": "keep"}],
        }]
        out, _ = await prepare_generation_messages(
            _prov("openrouter"),
            _body(samplers={"preserve_thinking": "all"}),
            msgs, _Provider(), "chat-1",
        )
        assert out[0]["reasoning_details"][0]["format"] == "anthropic-claude-v1"


class TestPreserveThinking:
    async def test_default_off_strips_reasoning(self):
        msgs = [{"role": "assistant", "content": "a", "reasoning": "thoughts"}]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"), _body(), msgs, _Provider(), "chat-1",
        )
        assert "reasoning" not in out[0]

    async def test_all_keeps_reasoning(self):
        msgs = [{"role": "assistant", "content": "a", "reasoning": "thoughts"}]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"), _body(samplers={"preserve_thinking": "all"}),
            msgs, _Provider(), "chat-1",
        )
        assert out[0]["reasoning"] == "thoughts"

    async def test_tool_only_strips_plain_assistant_reasoning(self):
        msgs = [{"role": "assistant", "content": "a", "reasoning": "thoughts"}]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"), _body(samplers={"preserve_thinking": "tool_only"}),
            msgs, _Provider(), "chat-1",
        )
        assert "reasoning" not in out[0]

    async def test_tool_only_keeps_reasoning_on_tool_call_turn(self):
        msgs = [{
            "role": "assistant",
            "content": "a",
            "reasoning": "thoughts",
            "tool_calls": [{"id": "1", "type": "function", "function": {"name": "t", "arguments": "{}"}}],
        }]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"), _body(samplers={"preserve_thinking": "tool_only"}),
            msgs, _Provider(), "chat-1",
        )
        assert out[0]["reasoning"] == "thoughts"

    async def test_preserve_thinking_is_forwarded_in_kwargs(self):
        # Not consumed here; the adapter drops it. Pinned as current behavior.
        _, kw = await prepare_generation_messages(
            _prov("openai_compat"), _body(samplers={"preserve_thinking": "all"}),
            [{"role": "user", "content": "hi"}], _Provider(), "chat-1",
        )
        assert kw["preserve_thinking"] == "all"


class TestPrefill:
    async def test_prefill_appended_on_continue(self):
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"),
            _body(samplers={}, regenerate=True, continue_text="partial reply"),
            msgs, _Provider(supports_prefill=True), "chat-1",
        )
        assert out[-1] == {"role": "assistant", "content": "partial reply"}

    async def test_prefill_carries_reasoning(self):
        msgs = [{"role": "user", "content": "hi"}]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"),
            _body(samplers={}, regenerate=True, continue_text="", continue_reasoning="thinking"),
            msgs, _Provider(supports_prefill=True), "chat-1",
        )
        assert out[-1] == {"role": "assistant", "content": "", "reasoning": "thinking"}

    async def test_prefill_not_appended_without_regenerate(self):
        msgs = [{"role": "user", "content": "hi"}]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"),
            _body(samplers={}, regenerate=False, continue_text="partial"),
            msgs, _Provider(supports_prefill=True), "chat-1",
        )
        assert out[-1]["role"] == "user"

    async def test_prefill_not_appended_when_unsupported(self):
        msgs = [{"role": "user", "content": "hi"}]
        out, _ = await prepare_generation_messages(
            _prov("google_aistudio"),
            _body(samplers={}, regenerate=True, continue_text="partial"),
            msgs, _Provider(supports_prefill=False), "chat-1",
        )
        assert out[-1]["role"] == "user"


class TestContextKwargs:
    async def test_openrouter_gets_session_id(self, monkeypatch):
        _patch_modalities(monkeypatch, None)
        _, kw = await prepare_generation_messages(
            _prov("openrouter"), _body(), [{"role": "user", "content": "hi"}], _Provider(), "chat-42",
        )
        assert kw["session_id"] == "chat-42"

    async def test_moonshot_gets_prompt_cache_key(self):
        _, kw = await prepare_generation_messages(
            _prov("moonshot"), _body(), [{"role": "user", "content": "hi"}], _Provider(), "chat-42",
        )
        assert kw["prompt_cache_key"] == "chat-42"

    async def test_other_types_get_no_context_kwargs(self):
        _, kw = await prepare_generation_messages(
            _prov("openai_compat"), _body(), [{"role": "user", "content": "hi"}], _Provider(), "chat-42",
        )
        assert "session_id" not in kw
        assert "prompt_cache_key" not in kw


class TestNativeReasoningRemap:
    async def test_deepseek_remaps_reasoning_to_native_key(self):
        msgs = [{"role": "assistant", "content": "a", "reasoning": "r"}]
        out, _ = await prepare_generation_messages(
            _prov("deepseek"), _body(samplers={"preserve_thinking": "all"}),
            msgs, _Provider(), "chat-1",
        )
        assert out[0]["reasoning_content"] == "r"
        assert "reasoning" not in out[0]

    async def test_moonshot_remaps_reasoning_to_native_key(self):
        msgs = [{"role": "assistant", "content": "a", "reasoning": "r"}]
        out, _ = await prepare_generation_messages(
            _prov("moonshot"), _body(samplers={"preserve_thinking": "all"}),
            msgs, _Provider(), "chat-1",
        )
        assert out[0]["reasoning_content"] == "r"
        assert "reasoning" not in out[0]

    async def test_xiaomi_mimo_remaps_reasoning_to_native_key(self):
        msgs = [{"role": "assistant", "content": "a", "reasoning": "r"}]
        out, _ = await prepare_generation_messages(
            _prov("xiaomi_mimo"), _body(samplers={"preserve_thinking": "all"}),
            msgs, _Provider(), "chat-1",
        )
        assert out[0]["reasoning_content"] == "r"
        assert "reasoning" not in out[0]

    async def test_remap_also_covers_the_continue_prefill(self):
        out, _ = await prepare_generation_messages(
            _prov("deepseek"),
            _body(samplers={}, regenerate=True, continue_text="", continue_reasoning="thinking"),
            [{"role": "user", "content": "hi"}], _Provider(), "chat-1",
        )
        assert out[-1]["reasoning_content"] == "thinking"
        assert "reasoning" not in out[-1]

    async def test_openai_compat_leaves_reasoning_untouched(self):
        msgs = [{"role": "assistant", "content": "a", "reasoning": "r"}]
        out, _ = await prepare_generation_messages(
            _prov("openai_compat"), _body(samplers={"preserve_thinking": "all"}),
            msgs, _Provider(), "chat-1",
        )
        assert out[0]["reasoning"] == "r"
        assert "reasoning_content" not in out[0]


class TestGoogleSafetyEndToEnd:
    async def test_safety_settings_reach_gen_kwargs_through_the_wrapper(self):
        _, kw = await prepare_generation_messages(
            _prov("openrouter", "google/gemini-3.8-flash"),
            _body(),
            [{"role": "user", "content": "hi"}], _Provider(), "chat-1",
        )
        assert kw["safety_settings"]
