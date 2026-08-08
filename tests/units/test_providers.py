"""Unit tests for the LLM provider implementations.

The OpenAI-compatible providers use the ``openai`` SDK internally, so
``_get_client`` is swapped for a fake client that captures the request
parameters and replays scripted streaming chunks (plain objects with the
attributes the provider accesses via ``getattr``). The Google providers
are tested in test_google_providers.py; ``fetch_models`` calls are tested
with ``httpx.MockTransport``.
"""

import json

import httpx
import pytest

from focus.core.utils import DEFAULT_MAX_TOKENS, DEFAULT_TEMPERATURE
from focus.providers import (
    BaseProvider,
    DeepseekProvider,
    MoonshotProvider,
    OpenAICompatProvider,
    OpenRouterProvider,
    create_provider,
)


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _delta(**kw) -> Obj:
    d = Obj(**kw)
    d.model_extra = None
    return d


def _chunk(*, content=None, tool_calls=None, reasoning=None, reasoning_content=None, usage=None) -> Obj:
    d = _delta(
        content=content,
        tool_calls=tool_calls,
        reasoning=reasoning,
        reasoning_content=reasoning_content,
    )
    return Obj(choices=[Obj(delta=d)], usage=usage)


def _usage(**kw) -> Obj:
    defaults = {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "prompt_tokens_details": None,
        "reasoning_tokens": None,
        "model_extra": None,
        "completion_tokens_details": None,
    }
    defaults.update(kw)
    return Obj(**defaults)


class FakeOpenAIClient:
    """Async-context-manager stand-in for AsyncOpenAI that captures the
    request kwargs and yields scripted chunks from ``create``."""

    def __init__(self, chunks=None):
        self.chunks = chunks or []
        self.request = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    async def create(self, **kwargs):
        self.request = kwargs

        async def _gen():
            for c in self.chunks:
                yield c

        return _gen()


async def _collect(provider, messages=None, **kwargs):
    out = []
    async for e in provider.stream_complete(messages or [{"role": "user", "content": "hi"}], **kwargs):
        out.append(e)
    return out


def _provider_with_fake_client(provider_cls, chunks, **init_kwargs):
    provider = provider_cls(**init_kwargs)
    client = FakeOpenAIClient(chunks)
    provider._get_client = lambda: client  # type: ignore[method-assign]
    return provider, client


class TestOpenAICompatProvider:
    def _make(self, chunks, **init_kwargs):
        return _provider_with_fake_client(
            OpenAICompatProvider,
            chunks,
            base_url="http://example.com/v1",
            api_key="sk-test",
            model="gpt-4o",
            params=init_kwargs.pop("params", {}),
            **init_kwargs,
        )

    async def test_token_stream_and_request_shape(self):
        provider, client = self._make([
            _chunk(content="Hello"),
            _chunk(content=" world"),
            _chunk(content="", usage=_usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)),
        ])
        events = await _collect(provider)

        assert [e for e in events if e["type"] == "token"] == [
            {"type": "token", "text": "Hello"}, {"type": "token", "text": " world"},
        ]
        usage = next(e["usage"] for e in events if e["type"] == "usage")
        assert usage["prompt_tokens"] == 10 and usage["completion_tokens"] == 5
        assert events[-1] == {"type": "done"}

        req = client.request
        assert req["model"] == "gpt-4o"
        assert req["stream"] is True
        assert req["max_tokens"] == DEFAULT_MAX_TOKENS
        assert req["temperature"] == DEFAULT_TEMPERATURE
        assert req["stream_options"] == {"include_usage": True}
        assert req["messages"] == [{"role": "user", "content": "hi"}]

    async def test_reasoning_delta_yields_meta_events(self):
        provider, _ = self._make([
            _chunk(reasoning_content="thinking…"),
            _chunk(content="answer"),
        ])
        events = await _collect(provider)
        assert {"type": "meta", "field": "reasoning", "value": "thinking…"} in events
        assert {"type": "token", "text": "answer"} in events

    async def test_reasoning_in_model_extra_yields_meta_event(self):
        provider, _ = self._make([
            _chunk(content="a", reasoning_content=None),
        ])
        provider._get_client()  # noqa: B018
        client = provider._get_client()
        chunk = _chunk(content="a")
        chunk.choices[0].delta.reasoning_content = None
        chunk.choices[0].delta.model_extra = {"reasoning_content": "extra-thought"}
        client.chunks = [chunk]
        events = await _collect(provider)
        assert {"type": "meta", "field": "reasoning", "value": "extra-thought"} in events

    async def test_o_model_uses_max_completion_tokens(self):
        provider, client = _provider_with_fake_client(
            OpenAICompatProvider, [_chunk(content="x")],
            base_url="http://x", api_key="k", model="o1-mini", params={},
        )
        await _collect(provider)
        req = client.request
        assert req["max_completion_tokens"] == DEFAULT_MAX_TOKENS
        assert "max_tokens" not in req
        assert "temperature" not in req

    async def test_unknown_sampler_kwargs_move_to_extra_body(self):
        provider, client = self._make([_chunk(content="x")], params={"seed": 42})
        await _collect(provider, top_p=0.9, rep_pen=1.2, no_repeat_ngram_size=3)
        req = client.request
        assert req["top_p"] == 0.9
        assert req["seed"] == 42
        assert req["extra_body"] == {"rep_pen": 1.2, "no_repeat_ngram_size": 3}

    async def test_tool_calls_accumulated_across_chunks(self):
        tc1 = Obj(index=0, id="call_1", function=Obj(name="read_file", arguments='{"path":'))
        tc2 = Obj(index=0, id="call_1", function=Obj(name=None, arguments=' "/x"}'))
        tc3 = Obj(index=1, id=None, function=Obj(name="list_dir", arguments='{"path": "/y"}'))
        provider, client = self._make([
            _chunk(tool_calls=[tc1]),
            _chunk(tool_calls=[tc2, tc3]),
        ])
        events = await _collect(provider)
        calls_event = next(e for e in events if e["type"] == "tool_calls")
        calls = calls_event["calls"]
        assert [c.id for c in calls] == ["call_1", ""]
        assert calls[0].name == "read_file"
        assert calls[0].arguments == {"path": "/x"}
        assert calls[1].name == "list_dir"
        assert calls[1].arguments == {"path": "/y"}
        assert all(e["type"] != "done" for e in events)

    async def test_malformed_tool_arguments_kept_raw(self):
        tc = Obj(index=0, id="c1", function=Obj(name="t", arguments="not json"))
        provider, _ = self._make([_chunk(tool_calls=[tc])])
        events = await _collect(provider)
        calls = next(e for e in events if e["type"] == "tool_calls")["calls"]
        assert calls[0].arguments == {"_raw": "not json"}

    async def test_usage_maps_cached_and_reasoning_tokens(self):
        usage = _usage(
            prompt_tokens=100, completion_tokens=50, total_tokens=150,
            prompt_tokens_details=Obj(cached_tokens=40),
            reasoning_tokens=None,
            model_extra={"reasoning_tokens": 30, "cost": 0.001, "cost_details": {"x": 1}},
            completion_tokens_details=None,
        )
        provider, _ = self._make([_chunk(content="x"), _chunk(content="", usage=usage)])
        events = await _collect(provider)
        usage_event = next(e for e in events if e["type"] == "usage")
        u = usage_event["usage"]
        assert u["cached_tokens"] == 40
        assert u["reasoning_tokens"] == 30
        assert u["cost"] == 0.001
        assert u["cost_details"] == {"x": 1}

    async def test_usage_reasoning_from_completion_details(self):
        usage = _usage(
            prompt_tokens=5, completion_tokens=5, total_tokens=10,
            prompt_tokens_details=None,
            reasoning_tokens=None,
            model_extra=None,
            completion_tokens_details=Obj(reasoning_tokens=7),
        )
        provider, _ = self._make([_chunk(content="", usage=usage)])
        events = await _collect(provider)
        u = next(e for e in events if e["type"] == "usage")["usage"]
        assert u["reasoning_tokens"] == 7
        assert u["cached_tokens"] == 0

    async def test_no_api_key_passes_no_key(self):
        provider = OpenAICompatProvider("http://x", "", "m", {})
        client = FakeOpenAIClient([_chunk(content="ok")])
        provider._get_client = lambda: client  # type: ignore[method-assign]
        await _collect(provider)
        assert client.request["model"] == "m"


class TestOpenRouterProvider:
    async def test_reasoning_config_and_preferences(self):
        provider = OpenRouterProvider(
            api_key="k", model="anthropic/claude-3.5-sonnet",
            params={"or_route": "r1", "or_quant": "q4", "or_no_fallbacks": True},
            site_url="https://example.com", app_name="FocusTest",
        )
        client = FakeOpenAIClient([_chunk(content="x")])
        provider._get_client = lambda: client  # type: ignore[method-assign]

        await _collect(provider, include_reasoning=True, reasoning_effort="high", thinking_budget=0)

        req = client.request
        assert req["extra_body"]["reasoning"] == {"effort": "high"}
        assert req["extra_body"]["provider"] == {
            "order": ["r1"], "quantizations": ["q4"], "allow_fallbacks": False,
        }
        assert "stream_options" not in req, "openrouter must not send stream_options"
        headers = provider._extra_headers()
        assert headers["HTTP-Referer"] == "https://example.com"
        assert headers["X-Title"] == "FocusTest"

    async def test_reasoning_budget_and_mode(self):
        provider = OpenRouterProvider(api_key="k", model="some/model", params={})
        client = FakeOpenAIClient([_chunk(content="x")])
        provider._get_client = lambda: client  # type: ignore[method-assign]

        await _collect(provider, include_reasoning=True, thinking_budget=500, reasoning_mode="focused")
        req = client.request
        assert req["extra_body"]["reasoning"] == {"max_tokens": 500, "mode": "focused"}

    async def test_reasoning_disabled(self):
        provider = OpenRouterProvider(api_key="k", model="m", params={})
        client = FakeOpenAIClient([_chunk(content="x")])
        provider._get_client = lambda: client  # type: ignore[method-assign]

        await _collect(provider, include_reasoning=False)
        assert client.request["extra_body"]["reasoning"] == {"enabled": False}

    async def test_fetch_models_uses_httpx(self, monkeypatch):
        captured = {}

        def handler(request):
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b"}]})

        _patch_httpx(monkeypatch, handler)
        provider = OpenRouterProvider(api_key="k", model="m", params={})
        models = await provider.fetch_models()
        assert [m["id"] for m in models] == ["a", "b"]
        assert captured["url"] == "https://openrouter.ai/api/v1/models"


class TestDeepseekProvider:
    async def test_thinking_and_prefix_mapping(self):
        provider = DeepseekProvider(api_key="k", model="deepseek-chat", params={})
        client = FakeOpenAIClient([_chunk(content="x")])
        provider._get_client = lambda: client  # type: ignore[method-assign]

        messages = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "prev", "reasoning": "hidden"},
        ]
        await _collect(provider, messages, include_reasoning=True)

        assert messages[1]["reasoning_content"] == "hidden"
        assert "reasoning" not in messages[1]
        assert messages[1]["prefix"] is True
        assert client.request["extra_body"]["thinking"] == {"type": "enabled"}
        assert provider.echoes_prefill is False

    async def test_thinking_disabled(self):
        provider = DeepseekProvider(api_key="k", model="m", params={})
        client = FakeOpenAIClient([_chunk(content="x")])
        provider._get_client = lambda: client  # type: ignore[method-assign]

        await _collect(provider, include_reasoning=False)
        assert client.request["extra_body"]["thinking"] == {"type": "disabled"}

    async def test_fetch_models_sends_auth_headers(self, monkeypatch):
        captured = {}

        def handler(request):
            captured["headers"] = dict(request.headers)
            return httpx.Response(200, json={"data": [{"id": "deepseek-chat"}]})

        _patch_httpx(monkeypatch, handler)
        provider = DeepseekProvider(api_key="sk-1", model="m", params={})
        models = await provider.fetch_models()
        assert [m["id"] for m in models] == ["deepseek-chat"]
        assert captured["headers"].get("authorization") == "Bearer sk-1"


class TestMoonshotProvider:
    async def test_thinking_keep_all_and_partial(self):
        provider = MoonshotProvider(api_key="k", model="moonshot-v1", params={})
        client = FakeOpenAIClient([_chunk(content="x")])
        provider._get_client = lambda: client  # type: ignore[method-assign]

        messages = [{"role": "assistant", "content": "prev", "reasoning": "r"}]
        await _collect(provider, messages, include_reasoning=True, preserve_thinking="all", reasoning_effort="high")

        assert messages[0]["reasoning_content"] == "r"
        assert "reasoning" not in messages[0]
        assert messages[-1]["partial"] is True
        req = client.request
        assert req["extra_body"]["thinking"] == {"type": "enabled", "keep": "all"}
        assert req["extra_body"]["reasoning_effort"] == "high"

    async def test_thinking_disabled(self):
        provider = MoonshotProvider(api_key="k", model="m", params={})
        client = FakeOpenAIClient([_chunk(content="x")])
        provider._get_client = lambda: client  # type: ignore[method-assign]

        await _collect(provider, include_reasoning=False)
        assert client.request["extra_body"]["thinking"] == {"type": "disabled"}


class _ConcreteProvider(BaseProvider):
    async def stream_complete(self, messages, **kwargs):
        yield {"type": "done"}


def _patch_httpx(monkeypatch, handler):
    """Replace httpx.AsyncClient with a MockTransport-backed one (capturing
    the real class first to avoid recursion inside the lambda)."""
    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **k: real(transport=httpx.MockTransport(handler)),
    )


class TestBaseProvider:
    def test_build_headers(self):
        assert _ConcreteProvider("http://x", "", "m", {})._build_headers() == {
            "Content-Type": "application/json",
        }
        headers = _ConcreteProvider("http://x", "k", "m", {})._build_headers()
        assert headers["Authorization"] == "Bearer k"

    async def test_fetch_models_variants(self, monkeypatch):
        provider = _ConcreteProvider("http://example.com", "k", "m", {})

        payloads = iter([
            {"data": [{"id": "a"}]},
            [{"id": "b"}],
            {"unrelated": True},
        ])

        def handler(request):
            return httpx.Response(200, json=next(payloads))

        _patch_httpx(monkeypatch, handler)
        assert await provider.fetch_models() == [{"id": "a"}]
        assert await provider.fetch_models() == [{"id": "b"}]
        assert await provider.fetch_models() == []

    async def test_fetch_models_http_error(self, monkeypatch):
        _patch_httpx(monkeypatch, lambda r: httpx.Response(500))
        provider = _ConcreteProvider("http://example.com", "k", "m", {})
        with pytest.raises(httpx.HTTPStatusError):
            await provider.fetch_models()


class TestCreateProvider:
    def test_all_types(self):
        cases = [
            ("openai_compat", OpenAICompatProvider),
            ("openrouter", OpenRouterProvider),
            ("deepseek", DeepseekProvider),
            ("moonshot", MoonshotProvider),
        ]
        for ptype, cls in cases:
            provider = create_provider({"type": ptype, "model": "m", "api_key": "", "base_url": "", "params_json": "{}"})
            assert isinstance(provider, cls), ptype

    def test_google_types(self, monkeypatch):
        from focus.providers import GoogleAIStudioProvider, GoogleVertexProvider

        monkeypatch.setattr("google.genai.Client", lambda **kw: ("client", kw))
        monkeypatch.setattr(
            "google.oauth2.service_account.Credentials.from_service_account_info",
            staticmethod(lambda info, scopes=None: "creds"),
        )
        monkeypatch.setattr("google.auth.default", lambda scopes=None: ("creds", "proj"))

        assert isinstance(
            create_provider({"type": "google_aistudio", "model": "m", "api_key": "", "base_url": "", "params_json": "{}"}),
            GoogleAIStudioProvider,
        )
        assert isinstance(
            create_provider({
                "type": "google_vertex", "model": "m", "api_key": "",
                "base_url": "",
                "params_json": json.dumps({"vertex_region": "us-central1", "vertex_project_id": "p"}),
            }),
            GoogleVertexProvider,
        )
        with pytest.raises(ValueError):
            # Vertex requires project/region in params
            create_provider({"type": "google_vertex", "model": "m", "api_key": "", "base_url": "", "params_json": "{}"})

    def test_default_openai_base_url(self):
        provider = create_provider({"type": "openai_compat", "model": "m", "api_key": "", "base_url": "", "params_json": "{}"})
        from focus.core.utils import DEFAULT_OPENAI_COMPAT_BASE_URL

        assert provider.base_url == DEFAULT_OPENAI_COMPAT_BASE_URL

    def test_corrupt_params_json(self):
        provider = create_provider({"type": "openai_compat", "model": "m", "api_key": "", "base_url": "http://x", "params_json": "{not json"})
        assert provider.params == {}

    def test_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown provider type"):
            create_provider({"type": "nope", "model": "m", "api_key": "", "base_url": "", "params_json": "{}"})
