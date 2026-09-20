"""Unit tests for provider multi-key resolution helpers.

These cover the pure selection logic (no DB): which list of refs a provider
exposes and which one is active. Secret resolution itself is exercised in
tests/api/test_providers_api.py.
"""

from focus.db.providers import active_key_ref, provider_key_refs


class TestProviderKeyRefs:
    def test_legacy_single_key_fallback(self):
        assert provider_key_refs({"api_key": "sk-legacy", "params_json": "{}"}) == ["sk-legacy"]

    def test_api_keys_take_precedence_over_legacy(self):
        row = {"api_key": "sk-legacy", "params_json": '{"api_keys": ["SECRET:a", "SECRET:b"]}'}
        assert provider_key_refs(row) == ["SECRET:a", "SECRET:b"]

    def test_empty_or_malformed_list_falls_back_to_legacy(self):
        for params in ("{}", '{"api_keys": []}', '{"api_keys": "nope"}', "not json", ""):
            row = {"api_key": "sk-legacy", "params_json": params}
            assert provider_key_refs(row) == ["sk-legacy"]

    def test_no_keys_at_all(self):
        assert provider_key_refs({"api_key": None, "params_json": "{}"}) == []

    def test_raw_keys_pass_through(self):
        row = {"params_json": '{"api_keys": ["SECRET:a", "sk-raw"]}'}
        assert provider_key_refs(row) == ["SECRET:a", "sk-raw"]


class TestActiveKeyRef:
    def test_defaults_to_first(self):
        row = {"params_json": '{"api_keys": ["SECRET:a", "SECRET:b"]}'}
        assert active_key_ref(row) == "SECRET:a"

    def test_explicit_active(self):
        row = {"params_json": '{"api_keys": ["SECRET:a", "SECRET:b"], "active_key": "SECRET:b"}'}
        assert active_key_ref(row) == "SECRET:b"

    def test_stale_active_falls_back_to_first(self):
        row = {"params_json": '{"api_keys": ["SECRET:a", "SECRET:b"], "active_key": "SECRET:gone"}'}
        assert active_key_ref(row) == "SECRET:a"

    def test_legacy_ref_is_active(self):
        assert active_key_ref({"api_key": "sk-legacy", "params_json": "{}"}) == "sk-legacy"

    def test_no_keys_is_none(self):
        assert active_key_ref({"api_key": None, "params_json": "{}"}) is None
