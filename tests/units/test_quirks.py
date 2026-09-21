"""Tests for the provider request-quirk pipeline itself.

These exercise the pipeline mechanics (ordering, applicability, dependency
injection, sampler stripping) directly. The end-to-end observable behavior is
still pinned by ``test_prepare_messages.py``; here we assert the structure that
makes adding a quirk a one-line change.
"""

from focus.core.models import StreamRequest
from focus.providers.google_safety import PASSTHROUGH_HARM_CATEGORIES
from focus.providers.quirks import QUIRKS, apply_request_quirks


class _Provider:
    def __init__(self, supports_prefill: bool = True):
        self.supports_prefill = supports_prefill


def _body(**kw) -> StreamRequest:
    return StreamRequest(chat_id="chat-1", **kw)


def _prov(ptype: str, model: str = "test-model") -> dict:
    return {"type": ptype, "model": model}


async def _run(prov, body, messages, provider=None, modality_lookup=None):
    return await apply_request_quirks(
        prov, body, messages, provider or _Provider(), "chat-1", modality_lookup,
    )


class TestPipelineStructure:
    def test_quirk_names_are_unique(self):
        names = [q.name for q in QUIRKS]
        assert len(names) == len(set(names))

    def test_prefill_is_ordered_after_the_stripping_quirks(self):
        names = [q.name for q in QUIRKS]
        assert names.index("append_prefill") > names.index("preserve_thinking")
        assert names.index("append_prefill") > names.index("strip_thought_signatures")
        # ...but before context kwargs, which only touch gen_kwargs.
        assert names.index("append_prefill") < names.index("context_kwargs")

    def test_modality_filtering_precedes_caching(self):
        names = [q.name for q in QUIRKS]
        assert names.index("filter_openrouter_modalities") < names.index("claude_cache")


class TestSamplerHandling:
    async def test_internal_keys_stripped_and_public_ones_forwarded(self):
        _, kw = await _run(
            _prov("openai_compat"),
            _body(samplers={
                "temperature": 0.5,
                "disable_multimodal": True,
                "image_format": "webp",
                "cache_enabled": True,
                "cache_ttl": "1h",
                "cache_depth": 2,
            }),
            [{"role": "user", "content": "hi"}],
        )
        assert kw == {"temperature": 0.5}

    async def test_context_kwargs_come_from_profile(self):
        _, kw = await _run(_prov("openrouter"), _body(), [{"role": "user", "content": "hi"}])
        assert kw["session_id"] == "chat-1"
        _, kw2 = await _run(_prov("moonshot"), _body(), [{"role": "user", "content": "hi"}])
        assert kw2["prompt_cache_key"] == "chat-1"

    async def test_context_kwargs_win_over_same_named_sampler(self):
        _, kw = await _run(
            _prov("openrouter"), _body(samplers={"session_id": "from-sampler"}),
            [{"role": "user", "content": "hi"}],
        )
        assert kw["session_id"] == "chat-1"


class TestInjectedModalityLookup:
    async def test_lookup_result_is_applied(self):
        called = {}

        async def lookup(model):
            called["model"] = model
            return ["text"]

        out, _ = await _run(
            _prov("openrouter", "google/gemini-x"),
            _body(),
            [{"role": "user", "content": [{"type": "text", "text": "x"}, {"type": "image_url", "image_url": {"url": "data:,"}}]}],
            modality_lookup=lookup,
        )
        assert called["model"] == "google/gemini-x"
        assert out[0]["content"] == "x"

    async def test_missing_lookup_is_a_noop(self):
        out, _ = await _run(
            _prov("openrouter"),
            _body(),
            [{"role": "user", "content": [{"type": "text", "text": "x"}, {"type": "image_url", "image_url": {"url": "data:,"}}]}],
            modality_lookup=None,
        )
        assert isinstance(out[0]["content"], list)

    async def test_lookup_is_not_called_for_non_openrouter(self):
        async def lookup(model):  # pragma: no cover - must not run
            raise AssertionError("lookup should not be called")

        await _run(_prov("openai_compat"), _body(), [{"role": "user", "content": "hi"}], modality_lookup=lookup)


class TestGoogleSafetyPassthrough:
    async def test_always_sends_full_payload_without_any_sampler(self):
        _, kw = await _run(
            _prov("openrouter", "google/gemini-3.8-flash"), _body(),
            [{"role": "user", "content": "hi"}],
        )
        assert [s["category"] for s in kw["safety_settings"]] == list(PASSTHROUGH_HARM_CATEGORIES)
        assert all(s["threshold"] == "OFF" for s in kw["safety_settings"])

    async def test_sent_for_gemma_too(self):
        _, kw = await _run(
            _prov("openrouter", "google/gemma-4-31b-it"), _body(),
            [{"role": "user", "content": "hi"}],
        )
        assert kw["safety_settings"]

    async def test_not_sent_for_non_google_model(self):
        _, kw = await _run(
            _prov("openrouter", "openai/gpt-4o"), _body(),
            [{"role": "user", "content": "hi"}],
        )
        assert "safety_settings" not in kw

    async def test_not_sent_for_native_google_provider(self):
        _, kw = await _run(
            _prov("google_aistudio"), _body(),
            [{"role": "user", "content": "hi"}],
        )
        assert "safety_settings" not in kw


class TestApplicability:
    async def test_thought_signatures_preserved_for_google(self):
        msgs = [{"role": "assistant", "content": "a", "thought_signature": "sig"}]
        out, _ = await _run(_prov("google_aistudio"), _body(), msgs)
        assert out[0]["thought_signature"] == "sig"

    async def test_thought_signatures_stripped_for_others(self):
        msgs = [{"role": "assistant", "content": "a", "thought_signature": "sig"}]
        out, _ = await _run(_prov("openai_compat"), _body(), msgs)
        assert "thought_signature" not in out[0]

    async def test_reasoning_details_quirk_skipped_for_openrouter_and_google(self):
        msgs = [{
            "role": "assistant",
            "content": "a",
            "reasoning_details": [{"format": "anthropic-claude-v1", "text": "keep"}],
        }]
        for ptype in ("openrouter", "google_aistudio", "google_vertex"):
            out, _ = await _run(_prov(ptype), _body(samplers={"preserve_thinking": "all"}), msgs)
            assert out[0]["reasoning_details"], ptype

    async def test_prefill_appended_only_when_supported(self):
        msgs = [{"role": "user", "content": "hi"}]
        out, _ = await _run(
            _prov("openai_compat"),
            _body(regenerate=True, continue_text="partial"),
            msgs,
            provider=_Provider(supports_prefill=True),
        )
        assert out[-1]["role"] == "assistant"
        out2, _ = await _run(
            _prov("google_aistudio"),
            _body(regenerate=True, continue_text="partial"),
            [{"role": "user", "content": "hi"}],
            provider=_Provider(supports_prefill=False),
        )
        assert out2[-1]["role"] == "user"
