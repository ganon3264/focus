"""Stability tests for the provider schema that feeds the frontend.

These pin the per-type defaults, effort options, and forwarding whitelist so a
provider/UI change can't silently alter what the sampler modal sends upstream.
"""

from focus.providers.registry import registered_types
from focus.providers.schema import BASE_SAMPLER_DEFAULTS, provider_schema, provider_type_options


class TestSchemaShape:
    def test_every_registered_type_has_an_entry(self):
        schema = provider_schema()
        for ptype in registered_types():
            assert ptype in schema["types"], ptype

    def test_capabilities_present_for_every_type(self):
        schema = provider_schema()
        for ptype, entry in schema["types"].items():
            caps = entry["capabilities"]
            assert "supports_tools" in caps, ptype
            assert "supports_prefill" in caps, ptype

    def test_openrouter_capabilities(self):
        caps = provider_schema()["types"]["openrouter"]["capabilities"]
        assert caps["supports_ephemeral_cache"] is True
        assert caps["include_stream_options"] is False
        assert caps["normalizes_reasoning"] is True

    def test_google_capabilities(self):
        for ptype in ("google_aistudio", "google_vertex"):
            caps = provider_schema()["types"][ptype]["capabilities"]
            assert caps["supports_prefill"] is False
            assert caps["thought_signatures"] is True
            assert caps["owns_reasoning"] is True
            assert caps["reasoning_formats"] is None

    def test_reasoning_message_key_is_declared(self):
        types = provider_schema()["types"]
        for ptype in ("deepseek", "moonshot"):
            assert types[ptype]["capabilities"]["reasoning_message_key"] == "reasoning_content"
        assert provider_schema()["types"]["openai_compat"]["capabilities"]["reasoning_message_key"] is None


class TestDefaults:
    def test_base_defaults(self):
        assert provider_schema()["baseDefaults"] == BASE_SAMPLER_DEFAULTS
        assert BASE_SAMPLER_DEFAULTS["image_format"] == "webp"
        assert BASE_SAMPLER_DEFAULTS["seed"] == -1

    def test_openai_compat_overrides_image_format_to_png(self):
        assert provider_schema()["types"]["openai_compat"]["defaults"] == {
            "preserve_thinking": "tool_only",
            "image_format": "png",
        }

    def test_openrouter_defaults(self):
        assert provider_schema()["types"]["openrouter"]["defaults"] == {
            "top_k": 0, "min_p": 0, "repetition_penalty": 1.0, "preserve_thinking": "tool_only",
        }

    def test_google_defaults_enable_reasoning(self):
        for ptype in ("google_aistudio", "google_vertex"):
            assert provider_schema()["types"][ptype]["defaults"] == {
                "include_reasoning": True,
                "reasoning_effort": "",
            }


class TestForwarding:
    def test_forward_lists(self):
        types = provider_schema()["types"]
        assert types["openai_compat"]["forwardAlways"] == [
            "frequency_penalty", "presence_penalty", "include_reasoning",
        ]
        assert types["openai_compat"]["forwardReasoning"] == ["reasoning_effort", "preserve_thinking"]
        assert types["deepseek"]["forwardAlways"] == ["include_reasoning"]
        assert types["deepseek"]["forwardReasoning"] == ["preserve_thinking"]
        assert types["openrouter"]["forwardAlways"] == [
            "top_k", "min_p", "repetition_penalty", "include_reasoning",
            "preserve_thinking", "top_a", "seed", "verbosity",
            "cache_enabled", "cache_ttl", "cache_depth",
        ]
        assert types["openrouter"]["forwardReasoning"] == ["reasoning_effort", "thinking_budget"]
        assert types["google_vertex"]["forwardAlways"] == ["top_k", "send_reasoning_history", "include_reasoning"]


class TestVisibility:
    def test_openrouter_visible_fields(self):
        visible = set(provider_schema()["types"]["openrouter"]["visible"])
        assert {"top_k", "reasoning_effort", "preserve_thinking", "cache_enabled", "include_reasoning"} <= visible

    def test_openai_compat_visible_fields(self):
        visible = set(provider_schema()["types"]["openai_compat"]["visible"])
        assert {"frequency_penalty", "include_reasoning", "reasoning_effort"} <= visible
        assert "top_k" not in visible

    def test_google_visible_fields(self):
        visible = set(provider_schema()["types"]["google_aistudio"]["visible"])
        assert {"top_k", "send_reasoning_history", "include_reasoning", "reasoning_effort"} <= visible


class TestEffortOptions:
    def test_openrouter_options(self):
        values = [o["value"] for o in provider_schema()["types"]["openrouter"]["effortOptions"]]
        assert values == ["minimal", "low", "medium", "high", "xhigh", "max"]

    def test_google_options_are_uppercase(self):
        for ptype in ("google_aistudio", "google_vertex"):
            values = [o["value"] for o in provider_schema()["types"][ptype]["effortOptions"]]
            assert values == ["MINIMAL", "LOW", "MEDIUM", "HIGH"]

    def test_openai_compat_options(self):
        values = [o["value"] for o in provider_schema()["types"]["openai_compat"]["effortOptions"]]
        assert values == ["low", "medium", "high"]


class TestFormAndTypeOptions:
    def test_provider_type_options_are_ordered_and_labeled(self):
        opts = provider_type_options()
        values = [o["value"] for o in opts]
        assert values[:3] == ["openai_compat", "openrouter", "google_aistudio"]
        assert opts[0]["label"] == "OpenAI Compatible"
        assert len(values) == len(set(values))

    def test_openrouter_form_hides_base_url_shows_or_fields(self):
        form = provider_schema()["types"]["openrouter"]["form"]
        assert form["orFields"] is True
        assert form["baseUrl"] is False

    def test_vertex_form_shows_vertex_fields(self):
        assert provider_schema()["types"]["google_vertex"]["form"]["vertexFields"] is True

    def test_openai_compat_uses_default_form(self):
        form = provider_schema()["types"]["openai_compat"]["form"]
        assert form["baseUrl"] is True
        assert form["orFields"] is False
