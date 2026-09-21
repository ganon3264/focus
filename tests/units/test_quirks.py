"""Tests for the provider request-quirk pipeline itself.

These exercise the pipeline mechanics (ordering, applicability, dependency
injection, sampler stripping) directly. The end-to-end observable behavior is
still pinned by ``test_prepare_messages.py``; here we assert the structure that
makes adding a quirk a one-line change.
"""

from focus.core.models import StreamRequest
from focus.providers.google_safety import PASSTHROUGH_HARM_CATEGORIES
from focus.providers.profile import Capabilities, ProviderProfile
from focus.providers.quirks import QUIRKS, apply_request_quirks


class _Provider:
    def __init__(
        self,
        supports_prefill: bool = True,
        modalities: list[str] | None = None,
        parameters: list[str] | None = None,
    ):
        self.supports_prefill = supports_prefill
        self._modalities = modalities
        self._parameters = parameters

    async def supported_modalities(self, model: str) -> list[str] | None:
        return self._modalities

    async def supported_parameters(self, model: str) -> list[str] | None:
        return self._parameters


def _body(**kw) -> StreamRequest:
    return StreamRequest(chat_id="chat-1", **kw)


def _prov(ptype: str, model: str = "test-model") -> dict:
    return {"type": ptype, "model": model}


async def _run(prov, body, messages, provider=None):
    return await apply_request_quirks(
        prov, body, messages, provider or _Provider(), "chat-1",
    )


class TestPipelineStructure:
    def test_quirk_names_are_unique(self):
        names = [q.name for q in QUIRKS]
        assert len(names) == len(set(names))

    def test_prefill_is_ordered_after_the_stripping_quirks(self):
        names = [q.name for q in QUIRKS]
        assert names.index("append_prefill") > names.index("preserve_thinking")
        assert names.index("append_prefill") > names.index("strip_thought_signatures")
        # The native-reasoning remap runs after the prefill append so the
        # synthesized assistant turn is remapped too...
        assert names.index("append_prefill") < names.index("remap_native_reasoning")
        # ...but before context kwargs, which only touch gen_kwargs.
        assert names.index("remap_native_reasoning") < names.index("context_kwargs")

    def test_modality_filtering_precedes_caching(self):
        names = [q.name for q in QUIRKS]
        assert names.index("filter_provider_modalities") < names.index("claude_cache")


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


class TestProviderModalities:
    async def test_provider_modalities_filter_media(self):
        out, _ = await _run(
            _prov("openrouter", "google/gemini-x"),
            _body(),
            [{"role": "user", "content": [{"type": "text", "text": "x"}, {"type": "image_url", "image_url": {"url": "data:,"}}]}],
            provider=_Provider(modalities=["text"]),
        )
        assert out[0]["content"] == "x"

    async def test_unknown_modalities_leave_messages_untouched(self):
        out, _ = await _run(
            _prov("openrouter"),
            _body(),
            [{"role": "user", "content": [{"type": "text", "text": "x"}, {"type": "image_url", "image_url": {"url": "data:,"}}]}],
        )
        assert isinstance(out[0]["content"], list)

    async def test_provider_is_consulted_for_every_type(self):
        # The provider (not a type check) is the single source of truth.
        seen = {}

        class RecordingProvider(_Provider):
            async def supported_modalities(self, model):
                seen["model"] = model
                return None

        await _run(
            _prov("openai_compat", "some-model"), _body(),
            [{"role": "user", "content": "hi"}], provider=RecordingProvider(),
        )
        assert seen["model"] == "some-model"


class TestSupportedParamFiltering:
    async def test_unsupported_wire_params_dropped(self):
        _, kw = await _run(
            _prov("openrouter", "xiaomi/mimo-v2.6-flash"),
            _body(samplers={"top_k": 0, "min_p": 0, "repetition_penalty": 1.0, "seed": 5, "top_p": 0.9}),
            [{"role": "user", "content": "hi"}],
            provider=_Provider(parameters=["top_p", "temperature", "include_reasoning"]),
        )
        assert kw == {"top_p": 0.9, "session_id": "chat-1"}

    async def test_reasoning_controls_survive_filtering(self):
        _, kw = await _run(
            _prov("openrouter"),
            _body(samplers={
                "include_reasoning": True, "reasoning_effort": "high",
                "preserve_thinking": "all", "top_k": 0,
            }),
            [{"role": "user", "content": "hi"}],
            provider=_Provider(parameters=["top_p"]),
        )
        assert kw["include_reasoning"] is True
        assert kw["reasoning_effort"] == "high"
        assert kw["preserve_thinking"] == "all"
        assert "top_k" not in kw

    async def test_unknown_capabilities_forward_everything(self):
        _, kw = await _run(
            _prov("openrouter"),
            _body(samplers={"top_k": 0, "min_p": 0}),
            [{"role": "user", "content": "hi"}],
            provider=_Provider(parameters=None),
        )
        assert kw["top_k"] == 0
        assert kw["min_p"] == 0

    async def test_provider_without_method_is_skipped(self):
        class Bare:
            supports_prefill = True

            async def supported_modalities(self, model):
                return None

        _, kw = await _run(
            _prov("openrouter"),
            _body(samplers={"top_k": 0}),
            [{"role": "user", "content": "hi"}],
            provider=Bare(),
        )
        assert kw["top_k"] == 0


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


class TestCapabilityDrivenQuirks:
    """A new provider becomes correct by declaring capabilities. These patch
    ``profile_for`` to simulate one without registering an adapter."""

    @staticmethod
    def _install(monkeypatch, caps):
        profile = ProviderProfile(caps=caps)
        monkeypatch.setattr("focus.providers.quirks.profile_for", lambda _ptype: profile)

    async def test_owns_reasoning_is_independent_of_thought_signatures(self, monkeypatch):
        self._install(monkeypatch, Capabilities(owns_reasoning=True, thought_signatures=False))
        msgs = [{"role": "assistant", "content": "a", "reasoning": "r", "thought_signature": "sig"}]
        out, _ = await _run(_prov("synthetic"), _body(samplers={"preserve_thinking": "off"}), msgs)
        assert out[0]["reasoning"] == "r"  # owns_reasoning -> preserve_thinking skipped
        assert "thought_signature" not in out[0]  # thought_signatures=False -> stripped

    async def test_thought_signatures_cap_keeps_the_field(self, monkeypatch):
        self._install(monkeypatch, Capabilities(thought_signatures=True))
        msgs = [{"role": "assistant", "content": "a", "thought_signature": "sig"}]
        out, _ = await _run(_prov("synthetic"), _body(), msgs)
        assert out[0]["thought_signature"] == "sig"

    async def test_reasoning_message_key_remaps(self, monkeypatch):
        self._install(monkeypatch, Capabilities(reasoning_message_key="thinking_field"))
        msgs = [{"role": "assistant", "content": "a", "reasoning": "r"}]
        out, _ = await _run(_prov("synthetic"), _body(samplers={"preserve_thinking": "all"}), msgs)
        assert out[0]["thinking_field"] == "r"
        assert "reasoning" not in out[0]

    async def test_no_reasoning_message_key_leaves_reasoning(self, monkeypatch):
        self._install(monkeypatch, Capabilities())
        msgs = [{"role": "assistant", "content": "a", "reasoning": "r"}]
        out, _ = await _run(_prov("synthetic"), _body(samplers={"preserve_thinking": "all"}), msgs)
        assert out[0]["reasoning"] == "r"
        assert "reasoning_content" not in out[0]

    async def test_normalizes_reasoning_drops_foreign_details(self, monkeypatch):
        self._install(monkeypatch, Capabilities(normalizes_reasoning=True))
        msgs = [{
            "role": "assistant",
            "content": "a",
            "reasoning_details": [{"format": "x"}],
            "_src_model": "other",
        }]
        out, _ = await _run(_prov("synthetic"), _body(samplers={"preserve_thinking": "all"}), msgs)
        assert out[0].get("reasoning_details") is None
        assert "_src_model" not in out[0]

    async def test_ephemeral_cache_is_capability_gated(self, monkeypatch):
        self._install(monkeypatch, Capabilities(supports_ephemeral_cache=True))
        msgs = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
        out, _ = await _run(
            _prov("synthetic", model="anthropic/claude-x"),
            _body(samplers={"cache_enabled": True}),
            msgs,
        )
        assert isinstance(out[0]["content"], list)
        assert out[0]["content"][0]["cache_control"]["type"] == "ephemeral"
