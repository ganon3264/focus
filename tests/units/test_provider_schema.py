"""The provider schema that feeds the sampler modal, the form and the quirks.

Every fact the UI depends on lives in ONE table (``TYPES``); a deliberate
change edits one row instead of scattering through twenty assertions. What the
schema cannot declare for itself — that capability filtering never swallows a
pipeline control, that the adapter class agrees with its profile — is asserted
as an invariant.
"""

import pytest

from focus.providers.profile import Capabilities
from focus.providers.registry import get_provider_class, registered_types
from focus.providers.schema import BASE_SAMPLER_DEFAULTS, provider_schema, provider_type_options

GOOGLE = ("google_aistudio", "google_vertex")

TYPES = {
    "openai_compat": {
        "caps": {"supports_prefill": True, "echoes_prefill": True, "supports_tools": True,
                 "include_stream_options": True, "reasoning_message_key": None},
        "defaults": {"preserve_thinking": "tool_only", "image_format": "png"},
        "forward_always": ["frequency_penalty", "presence_penalty", "include_reasoning"],
        "forward_reasoning": ["reasoning_effort", "preserve_thinking"],
        "effort": ["low", "medium", "high"],
        "visible": {"frequency_penalty", "include_reasoning", "reasoning_effort"},
        "form": {"baseUrl": True, "orFields": False},
    },
    "openrouter": {
        "caps": {"supports_ephemeral_cache": True, "include_stream_options": False,
                 "normalizes_reasoning": True},
        "defaults": {"top_k": 0, "min_p": 0, "repetition_penalty": 1.0,
                     "preserve_thinking": "tool_only"},
        "forward_always": [
            "top_k", "min_p", "repetition_penalty", "include_reasoning",
            "preserve_thinking", "seed", "verbosity",
            "cache_enabled", "cache_ttl", "cache_depth", "echo_upstream_body",
        ],
        "forward_reasoning": ["reasoning_effort", "thinking_budget"],
        "effort": ["minimal", "low", "medium", "high", "xhigh", "max"],
        "visible": {"top_k", "reasoning_effort", "preserve_thinking", "cache_enabled",
                    "include_reasoning"},
        "form": {"orFields": True, "baseUrl": False},
    },
    "nanogpt": {
        "caps": {"supports_ephemeral_cache": True,
                 "cache_breakpoint_models": ("anthropic/claude", "google/gemini"),
                 "normalizes_reasoning": True},
        "defaults": {"top_k": 0, "min_p": 0, "repetition_penalty": 1.0,
                     "preserve_thinking": "tool_only"},
        "forward_always": [
            "top_k", "min_p", "repetition_penalty", "include_reasoning",
            "preserve_thinking", "seed", "cache_enabled", "cache_ttl", "cache_depth",
        ],
        "forward_reasoning": ["reasoning_effort"],
        "effort": ["minimal", "low", "medium", "high", "xhigh", "max"],
        "visible": set(),
        "form": {"ngFields": True, "orFields": False, "baseUrl": False, "modelRequired": True},
    },
    "deepseek": {
        "caps": {"reasoning_message_key": "reasoning_content", "echoes_prefill": False,
                 "supports_prefill": True},
        "defaults": {},
        "forward_always": ["include_reasoning"],
        "forward_reasoning": ["preserve_thinking"],
        "effort": None,
        "visible": set(),
        "form": {},
    },
    "moonshot": {
        "caps": {"reasoning_message_key": "reasoning_content", "echoes_prefill": False},
        "defaults": {},
        "forward_always": None,
        "forward_reasoning": None,
        "effort": None,
        "visible": set(),
        "form": {},
    },
    "xiaomi_mimo": {
        "caps": {"reasoning_message_key": "reasoning_content", "echoes_prefill": False,
                 "supports_prefill": True, "reasoning_formats": ()},
        "defaults": {},
        "forward_always": ["frequency_penalty", "presence_penalty", "include_reasoning"],
        "forward_reasoning": ["preserve_thinking"],
        "effort": None,
        "visible": set(),
        "form": {},
    },
    "google_aistudio": {
        "caps": {"supports_prefill": False, "supports_tools": True, "thought_signatures": True,
                 "owns_reasoning": True, "reasoning_formats": None},
        "defaults": {"include_reasoning": True, "reasoning_effort": ""},
        "forward_always": None,
        "forward_reasoning": None,
        "effort": ["MINIMAL", "LOW", "MEDIUM", "HIGH"],
        "visible": {"top_k", "send_reasoning_history", "include_reasoning", "reasoning_effort"},
        "form": {},
    },
    "google_vertex": {
        "caps": {"supports_prefill": False, "thought_signatures": True, "owns_reasoning": True,
                 "reasoning_formats": None},
        "defaults": {"include_reasoning": True, "reasoning_effort": ""},
        "forward_always": ["top_k", "send_reasoning_history", "include_reasoning"],
        "forward_reasoning": None,
        "effort": ["MINIMAL", "LOW", "MEDIUM", "HIGH"],
        "visible": set(),
        "form": {"vertexFields": True},
    },
}


def _entry(ptype: str) -> dict:
    return provider_schema()["types"][ptype]


def test_every_registered_type_is_declared():
    """The schema and the adapter registry must agree, in both directions."""
    declared = set(provider_schema()["types"])
    assert declared == set(registered_types())
    assert declared == set(TYPES), "a provider type is missing from TYPES"


@pytest.mark.parametrize("ptype", sorted(TYPES))
def test_type_facts(ptype):
    entry = _entry(ptype)
    expected = TYPES[ptype]

    for key, value in expected["caps"].items():
        assert entry["capabilities"][key] == value, f"{ptype}.{key}"

    if expected["defaults"]:
        assert entry["defaults"] == expected["defaults"], f"{ptype} defaults"

    if expected["forward_always"] is not None:
        assert entry["forwardAlways"] == expected["forward_always"], f"{ptype} forwardAlways"
    if expected["forward_reasoning"] is not None:
        assert entry["forwardReasoning"] == expected["forward_reasoning"], f"{ptype} forwardReasoning"

    if expected["effort"] is not None:
        assert [o["value"] for o in entry["effortOptions"]] == expected["effort"]

    if expected["visible"]:
        assert expected["visible"] <= set(entry["visible"]), f"{ptype} visible fields"

    for key, value in expected["form"].items():
        assert entry["form"][key] == value, f"{ptype}.form.{key}"


def test_openai_compat_visible_excludes_unsupported_samplers():
    visible = set(_entry("openai_compat")["visible"])
    assert "top_k" not in visible


def test_capability_filtered_never_carries_pipeline_controls():
    """Keys the request pipeline consumes are stripped centrally; filtering them
    against a provider's advertised parameters too would silently drop them."""
    pipeline_controls = {
        "include_reasoning", "preserve_thinking", "reasoning_effort",
        "thinking_budget", "send_reasoning_history", "echo_upstream_body",
    }
    for ptype in registered_types():
        filtered = set(_entry(ptype)["capabilityFiltered"])
        assert not (filtered & pipeline_controls), f"{ptype} filters a pipeline control"


def test_capability_filtered_is_what_openrouter_advertises():
    assert set(_entry("openrouter")["capabilityFiltered"]) == {
        "top_k", "min_p", "repetition_penalty", "seed", "verbosity",
    }
    assert set(_entry("openai_compat")["capabilityFiltered"]) == {
        "frequency_penalty", "presence_penalty",
    }


def test_base_defaults_are_the_documented_sampler_defaults():
    schema = provider_schema()
    assert schema["baseDefaults"] == BASE_SAMPLER_DEFAULTS
    assert BASE_SAMPLER_DEFAULTS["image_format"] == "webp"
    assert BASE_SAMPLER_DEFAULTS["seed"] == -1


def test_cache_breakpoint_transports_share_the_model_list():
    """The sampler and the quirk read the same prefixes, and the fixed-TTL
    families ride the schema so the UI can hide the extra-hour sampler."""
    schema = provider_schema()
    breakpoints = schema["types"]["openrouter"]["capabilities"]["cache_breakpoint_models"]
    assert "anthropic/claude" in breakpoints and "google/gemini" in breakpoints
    assert schema["fixedCacheTtlModels"] == ["google/"]


def test_provider_type_options_are_ordered_and_unique():
    opts = provider_type_options()
    values = [o["value"] for o in opts]
    assert values[:3] == ["openai_compat", "openrouter", "nanogpt"]
    assert opts[0]["label"] == "OpenAI Compatible"
    assert len(values) == len(set(values))


@pytest.mark.parametrize("ptype", registered_types())
def test_adapter_class_agrees_with_its_profile(ptype):
    """The schema publishes the profile; the class copies it at registration.
    A type whose class and profile disagree sends the wrong capabilities
    downstream (tool calls, prefill echo, caching)."""
    cls = get_provider_class(ptype)
    caps = _entry(ptype)["capabilities"]
    assert cls.type == ptype
    assert isinstance(cls.profile.caps, Capabilities)
    for attr in ("supports_tools", "supports_prefill", "echoes_prefill"):
        assert getattr(cls, attr) == getattr(cls.profile.caps, attr), f"{ptype}.{attr}"
        assert caps[attr] == getattr(cls.profile.caps, attr), f"schema {ptype}.{attr}"
