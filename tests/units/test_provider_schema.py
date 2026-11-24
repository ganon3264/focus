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


def _entry(ptype: str) -> dict:
    return provider_schema()["types"][ptype]


def test_every_registered_type_is_declared():
    """The schema and the adapter registry must agree, in both directions."""
    declared = set(provider_schema()["types"])
    assert declared == set(registered_types())


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


def test_base_defaults_pin_documented_values():
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
