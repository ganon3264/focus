"""Unit tests for the Google Gemini providers (focus/providers/google_*).

``_build_contents``/``_build_parts`` are pure functions and are tested
directly. ``_do_stream``/``stream_complete`` use a fake client object whose
``aio.models.generate_content_stream`` replays scripted chunks. The Vertex
constructor's credential plumbing is exercised with stubbed
``google.auth.default`` / ``from_service_account_info`` / ``genai.Client``.
"""

import base64
import json

import pytest

from focus.providers import GoogleAIStudioProvider, GoogleVertexProvider
from focus.providers.google_base import GoogleProviderBase


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _base():
    return _make_provider()


def _make_provider(cls=GoogleProviderBase, api_key="k", model="m", params=None):
    """Instance without running the real constructor (no SDK client)."""
    provider = cls.__new__(cls)
    provider.model = model
    provider.api_key = api_key
    provider.params = params or {}
    provider._pending_thought_signatures = {}
    if cls is GoogleVertexProvider:
        provider.project_id = "proj"
        provider.region = "us-central1"
    return provider


class FakeGenAIClient:
    """Stand-in for genai.Client capturing the generate_content_stream args."""

    def __init__(self, chunks=None):
        self.chunks = chunks or []
        self.config = None
        self.contents = None
        self.model = None

    @property
    def aio(self):
        return self

    @property
    def models(self):
        return self

    async def generate_content_stream(self, model, contents, config):
        self.model = model
        self.contents = contents
        self.config = config

        async def _gen():
            for c in self.chunks:
                yield c

        return _gen()


async def _collect(provider, messages=None, **kwargs):
    out = []
    async for e in provider.stream_complete(messages or [{"role": "user", "content": "hi"}], **kwargs):
        out.append(e)
    return out


class TestBuildParts:
    def test_plain_string(self):
        parts = GoogleProviderBase._build_parts("hello")
        assert len(parts) == 1
        assert parts[0].text == "hello"
        assert parts[0].thought is not True

    def test_with_reasoning_and_signature(self):
        sig = base64.b64encode(b"sig-bytes").decode()
        parts = GoogleProviderBase._build_parts("answer", reasoning="think", thought_signature_b64=sig)
        assert parts[0].text == "think"
        assert parts[0].thought is True
        assert parts[1].text == "answer"
        assert parts[1].thought_signature == b"sig-bytes"

    def test_content_list_with_image_data_url(self):
        img_b64 = base64.b64encode(b"\x89PNG fake").decode()
        content = [
            {"type": "text", "text": "see this"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
        ]
        parts = GoogleProviderBase._build_parts(content)
        assert parts[0].text == "see this"
        image_part = parts[1]
        assert image_part.inline_data is not None
        assert image_part.inline_data.mime_type == "image/png"
        assert image_part.inline_data.data == b"\x89PNG fake"

    def test_signature_attached_to_first_text_part(self):
        sig = base64.b64encode(b"s").decode()
        content = [
            {"type": "text", "text": "a"},
            {"type": "text", "text": "b"},
        ]
        parts = GoogleProviderBase._build_parts(content, thought_signature_b64=sig)
        assert parts[0].thought_signature == b"s"
        assert parts[1].thought_signature is None

    def test_non_text_non_image_parts_skipped(self):
        parts = GoogleProviderBase._build_parts([{"type": "input_audio", "input_audio": {}}])
        assert parts == []


class TestExtractText:
    def test_string(self):
        assert GoogleProviderBase._extract_text("hi") == "hi"

    def test_list(self):
        content = [
            {"type": "text", "text": "a"},
            {"type": "image_url", "image_url": {"url": "x"}},
            {"type": "text", "text": "b"},
        ]
        assert GoogleProviderBase._extract_text(content) == "a\nb"

    def test_other(self):
        assert GoogleProviderBase._extract_text(42) == "42"


class TestToGoogleTools:
    def test_empty_returns_none(self):
        assert GoogleProviderBase._to_google_tools([]) is None
        assert GoogleProviderBase._to_google_tools(None) is None

    def test_converts_declarations(self):
        tools = GoogleProviderBase._to_google_tools([
            {"type": "function", "function": {
                "name": "read_file", "description": "Read a file",
                "parameters": {"type": "object", "properties": {"path": {"type": "string"}}},
            }},
        ])
        assert tools is not None
        fn = tools[0].function_declarations[0]
        assert fn.name == "read_file"
        assert fn.description == "Read a file"


class TestBuildContents:
    def test_system_messages_concatenated(self):
        messages = [
            {"role": "system", "content": "You are"},
            {"role": "system", "content": " helpful."},
            {"role": "user", "content": "hi"},
        ]
        system, contents = _base()._build_contents(messages, {}, None, True)
        assert system == "You are\n\n helpful."
        assert [c.role for c in contents] == ["user"]

    def test_assistant_reasoning_conditioned_on_send_reasoning_history(self):
        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "ans", "reasoning": "think"},
        ]
        _, contents = _base()._build_contents(messages, {"send_reasoning_history": False}, None, True)
        model_parts = contents[1].parts
        assert [p.thought for p in model_parts if p.text == "ans"] == [None]
        assert not [p for p in model_parts if p.thought]

        _, contents = _base()._build_contents(messages, {"send_reasoning_history": True}, None, True)
        model_parts = contents[1].parts
        assert any(p.thought and p.text == "think" for p in model_parts)

    def test_thought_signature_only_on_last_assistant(self):
        s1 = base64.b64encode(b"s1").decode()
        s2 = base64.b64encode(b"s2").decode()
        messages = [
            {"role": "assistant", "content": "old", "thought_signature": s1},
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "new", "thought_signature": s2},
        ]
        _, contents = _base()._build_contents(messages, {"send_reasoning_history": True}, 2, True)
        first_parts = contents[0].parts
        assert first_parts[0].thought_signature is None
        last_parts = contents[2].parts
        assert last_parts[0].thought_signature == b"s2"

    def test_tool_calls_and_tool_role(self):
        messages = [
            {"role": "assistant", "content": "",
             "tool_calls": [{"id": "fc1", "function": {"name": "read_file", "arguments": '{"path": "/x"}'}}]},
            {"role": "tool", "tool_call_id": "fc1", "content": "file content"},
        ]
        _, contents = _base()._build_contents(messages, {}, None, True)
        model = contents[0]
        assert model.role == "model"
        fc_part = next(p.function_call for p in model.parts if p.function_call)
        assert fc_part.id == "fc1"
        assert fc_part.name == "read_file"
        assert fc_part.args == {"path": "/x"}

        tool = contents[1]
        assert tool.role == "user"
        fr = tool.parts[0].function_response
        assert fr.id == "fc1"
        assert fr.name == "read_file"
        assert fr.response == {"result": "file content"}

    def test_inject_pending_signatures(self):
        provider = _make_provider()
        provider._pending_thought_signatures = {"fc1": b"sig"}
        messages = [{"tool_calls": [{"id": "fc1", "function": {"name": "x"}}]}]
        provider._inject_pending_signatures(messages)
        assert messages[0]["tool_calls"][0]["_thought_signature"] == b"sig"
        assert provider._pending_thought_signatures == {}

    def test_find_last_assistant_with_signature(self):
        provider = _make_provider()
        messages = [
            {"role": "assistant", "content": "a", "thought_signature": b"s1"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "b"},
        ]
        assert provider._find_last_assistant_with_signature(messages) == 0
        assert provider._find_last_assistant_with_signature([{"role": "user", "content": "u"}]) is None


class TestDoStream:
    def _provider_with_client(self, chunks):
        provider = _make_provider()
        provider.client = FakeGenAIClient(chunks)
        provider._build_config = lambda *a, **k: None
        return provider

    async def test_text_and_thought_parts(self):
        provider = self._provider_with_client([
            Obj(usage_metadata=None, candidates=[Obj(content=Obj(parts=[
                Obj(function_call=None, text="visible", thought=False, thought_signature=None),
                Obj(function_call=None, text="hidden", thought=True, thought_signature=None),
            ]))]),
            Obj(usage_metadata=Obj(prompt_token_count=10, candidates_token_count=5, total_token_count=15, cached_content_token_count=2),
                candidates=[Obj(content=Obj(parts=[]))]),
        ])
        events = await _collect(provider)
        assert events[0] == {"type": "token", "text": "visible"}
        assert events[1] == {"type": "meta", "field": "reasoning", "value": "hidden"}
        usage = next(e for e in events if e["type"] == "usage")["usage"]
        assert usage["prompt_tokens"] == 10
        assert usage["cached_tokens"] == 2

    async def test_function_call_accumulation_and_signature_capture(self):
        provider = self._provider_with_client([
            Obj(usage_metadata=None, candidates=[Obj(content=Obj(parts=[
                Obj(function_call=Obj(id="fc1", name="read_file", args={"path": "/a"}),
                    text=None, thought=False, thought_signature=b"sig1"),
            ]))]),
            Obj(usage_metadata=None, candidates=[Obj(content=Obj(parts=[]))]),
        ])
        events = await _collect(provider)
        calls = next(e for e in events if e["type"] == "tool_calls")["calls"]
        assert len(calls) == 1
        assert calls[0].id == "fc1"
        assert calls[0].name == "read_file"
        assert calls[0].arguments == {"path": "/a"}
        assert provider._pending_thought_signatures == {"fc1": b"sig1"}

    async def test_empty_chunks_yield_nothing(self):
        provider = self._provider_with_client([Obj(usage_metadata=None, candidates=[])])
        events = await _collect(provider)
        assert events == [{"type": "done"}]


class TestStreamComplete:
    async def test_yields_done_and_builds_config(self, monkeypatch):
        provider = _make_provider()
        client = FakeGenAIClient([
            Obj(usage_metadata=None, candidates=[Obj(content=Obj(parts=[
                Obj(function_call=None, text="hi", thought=False, thought_signature=None),
            ]))]),
        ])
        provider.client = client
        monkeypatch.setattr(provider, "_build_config", lambda merged, system_instruction, **kw: "cfg")

        events = await _collect(provider)
        assert [e["type"] for e in events] == ["token", "done"]
        assert client.config == "cfg"

    async def test_retries_without_signature_on_failure(self, monkeypatch):
        provider = _make_provider()
        calls = []

        async def fake_do_stream(contents, config):
            calls.append(contents)
            if len(calls) == 1:
                raise RuntimeError("signature rejected")
            yield {"type": "token", "text": "retried"}

        monkeypatch.setattr(provider, "_do_stream", fake_do_stream)
        monkeypatch.setattr(provider, "_build_config", lambda *a, **k: None)
        messages = [
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "prev", "thought_signature": base64.b64encode(b"s").decode()},
        ]
        events = await _collect(provider, messages)
        assert [e["type"] for e in events] == ["token", "done"]
        assert len(calls) == 2

    async def test_failure_without_signature_reraises(self, monkeypatch):
        provider = _make_provider()
        monkeypatch.setattr(provider, "_build_config", lambda *a, **k: None)

        async def boom(contents, config):
            raise RuntimeError("fail")
            yield  # pragma: no cover

        monkeypatch.setattr(provider, "_do_stream", boom)
        with pytest.raises(RuntimeError):
            await _collect(provider, [{"role": "user", "content": "q"}])

    async def test_tools_converted_for_google(self, monkeypatch):
        provider = _make_provider()
        client = FakeGenAIClient([])
        provider.client = client
        captured = {}

        def fake_build_config(merged, system_instruction, **kw):
            captured["google_tools"] = kw.get("google_tools")
            return None

        monkeypatch.setattr(provider, "_build_config", fake_build_config)
        await _collect(provider, tools=[{"type": "function", "function": {"name": "f", "description": "d"}}])
        assert captured["google_tools"] is not None


class TestAIStudioConfig:
    def test_build_config_defaults(self):
        provider = _make_provider(GoogleAIStudioProvider)
        config = provider._build_config({}, None)
        assert config.top_p == 1.0
        assert config.top_k == 0
        assert config.system_instruction is None

    def test_build_config_max_tokens_and_stop(self):
        provider = _make_provider(GoogleAIStudioProvider)
        config = provider._build_config({"max_tokens": 500, "stop": "END"}, "sys")
        assert config.max_output_tokens == 500
        assert config.stop_sequences == ["END"]
        assert config.system_instruction == "sys"

    def test_build_config_tools(self):
        provider = _make_provider(GoogleAIStudioProvider)
        from google.genai import types

        config = provider._build_config({}, None, google_tools=[types.Tool()])
        assert config.tools == [types.Tool()]
        assert config.tool_config.function_calling_config.mode == "AUTO"

    def test_thinking_config(self):
        provider = _make_provider(GoogleAIStudioProvider)
        config = provider._build_config({"include_reasoning": True, "reasoning_effort": "low"}, None)
        assert config.thinking_config.include_thoughts is True
        assert config.thinking_config.thinking_level.value == "LOW"

        config = provider._build_config({"include_reasoning": False}, None)
        assert config.thinking_config.include_thoughts is False

        config = provider._build_config({}, None)
        assert config.thinking_config.include_thoughts is True

    def test_client_uses_api_key(self, monkeypatch):
        captured = {}
        monkeypatch.setattr("google.genai.Client", lambda **kw: captured.update(kw) or ("c", kw))
        GoogleAIStudioProvider("k123", "m", {})
        assert captured["api_key"] == "k123"

    def test_client_falls_back_to_env_key(self, monkeypatch):
        captured = {}
        monkeypatch.setattr("google.genai.Client", lambda **kw: captured.update(kw) or ("c", kw))
        monkeypatch.setenv("GEMINI_API_KEY", "env-key")
        GoogleAIStudioProvider("", "m", {})
        assert captured["api_key"] == "env-key"

    async def test_fetch_models(self):
        provider = _make_provider(GoogleAIStudioProvider)

        class FakeModels:
            async def list(self):
                async def _gen():
                    yield Obj(name="models/gemini-2.0-flash")
                    yield Obj(name="plain")

                return _gen()

        provider.client = Obj(aio=Obj(models=FakeModels()))
        models = await provider.fetch_models()
        assert models == [{"id": "gemini-2.0-flash", "name": "gemini-2.0-flash"},
                          {"id": "plain", "name": "plain"}]


class TestVertexConfig:
    def test_build_config(self):
        provider = _make_provider(GoogleVertexProvider)
        config = provider._build_config({"stop": "END", "top_p": 0.9, "top_k": 40, "max_tokens": 1000}, "sys")
        assert config.max_output_tokens == 1000
        assert config.top_p == 0.9
        assert config.top_k == 40
        assert config.stop_sequences == ["END"]
        assert config.system_instruction == "sys"

    def test_build_config_defaults_omit_optional(self):
        provider = _make_provider(GoogleVertexProvider)
        config = provider._build_config({}, None)
        assert config.max_output_tokens is not None
        assert config.system_instruction is None

    def test_build_config_thinking(self):
        provider = _make_provider(GoogleVertexProvider)
        config = provider._build_config({"include_reasoning": "true"}, None)
        assert config.thinking_config.include_thoughts is True

        config = provider._build_config({"include_reasoning": False}, None)
        assert config.thinking_config.include_thoughts is False


class TestVertexConstructor:
    def _patch_deps(self, monkeypatch, *, sa_creds=None, adc_creds=None, client_factory=None):
        monkeypatch.setattr(
            "google.oauth2.service_account.Credentials.from_service_account_info",
            staticmethod(lambda info, scopes=None: sa_creds),
        )
        monkeypatch.setattr("google.auth.default", lambda scopes=None: adc_creds)
        monkeypatch.setattr("google.genai.Client", client_factory or (lambda **kw: ("client", kw)))

    def test_service_account_json_api_key(self, monkeypatch):
        captured = {}
        self._patch_deps(monkeypatch, sa_creds="sa-creds", client_factory=lambda **kw: captured.update(kw) or ("c", kw))
        sa_json = json.dumps({
            "type": "service_account", "project_id": "sa-proj", "client_email": "x@y",
            "private_key": "k", "token_uri": "https://oauth2.googleapis.com/token",
        })
        provider = GoogleVertexProvider(sa_json, "gemini-m", {"vertex_region": "us-central1"})
        assert provider.credentials == "sa-creds"
        assert provider.project_id == "sa-proj"
        assert provider.region == "us-central1"
        assert captured["vertexai"] is True
        assert captured["project"] == "sa-proj"
        assert captured["location"] == "us-central1"

    def test_adc_fallback(self, monkeypatch):
        captured = {}
        self._patch_deps(monkeypatch, adc_creds=("adc-creds", "adc-proj"), client_factory=lambda **kw: captured.update(kw) or ("c", kw))
        provider = GoogleVertexProvider("", "gemini-m", {"vertex_region": "us-east1"})
        assert provider.credentials == "adc-creds"
        assert provider.project_id == "adc-proj"
        assert captured["project"] == "adc-proj"

    def test_missing_region_raises(self, monkeypatch):
        self._patch_deps(monkeypatch, adc_creds=("c", "p"))
        with pytest.raises(ValueError, match="Project ID and Region"):
            GoogleVertexProvider("", "m", {})

    def test_malformed_service_account_raises(self, monkeypatch):
        self._patch_deps(monkeypatch, sa_creds="c")
        with pytest.raises(ValueError, match="Failed to parse api_key"):
            GoogleVertexProvider("{not json", "m", {"vertex_region": "r", "vertex_project_id": "p"})

    def test_adc_failure_raises(self, monkeypatch):
        monkeypatch.setattr("google.genai.Client", lambda **kw: None)

        def fail_default(scopes=None):
            raise RuntimeError("no creds")

        monkeypatch.setattr("google.auth.default", fail_default)
        with pytest.raises(ValueError, match="ADC credentials"):
            GoogleVertexProvider("", "m", {"vertex_region": "r", "vertex_project_id": "p"})

    async def test_fetch_models(self):
        provider = _make_provider(GoogleVertexProvider)

        class FakeModels:
            async def list(self):
                async def _gen():
                    yield Obj(name="projects/p/locations/us-central1/publishers/google/models/gemini-2.0-flash")

                return _gen()

        provider.client = Obj(aio=Obj(models=FakeModels()))
        models = await provider.fetch_models()
        assert models == [{"id": "gemini-2.0-flash", "name": "gemini-2.0-flash"}]
