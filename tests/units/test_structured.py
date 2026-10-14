from __future__ import annotations

import pytest

from focus.core.structured import (
    build_response_format,
    parse_structured,
    render_structured,
    resolve_schema,
    validate_schema_text,
    validate_template,
)


class TestResolveSchema:
    def test_substitutes_macros_in_strings_and_keys(self):
        schema = resolve_schema(
            '{"properties":{"{{field}}":{"type":"string","description":"As {{char}}"}},"required":["{{field}}"]}',
            {"field": "name", "char": "Alice"},
        )
        assert list(schema["properties"]) == ["name"]
        assert schema["properties"]["name"]["description"] == "As Alice"
        assert schema["required"] == ["name"]

    def test_preserves_non_string_types(self):
        schema = resolve_schema(
            '{"strict":true,"count":3,"empty":null,"items":[false,2,"{{limit}}"]}',
            {"limit": "10"},
        )
        assert schema == {
            "strict": True,
            "count": 3,
            "empty": None,
            "items": [False, 2, "10"],
        }

    def test_invalid_source_json_raises_before_macros(self):
        with pytest.raises(ValueError):
            resolve_schema('{"maxLength": {{getvar::limit}}}', {"getvar::limit": "10"})

    def test_rejects_duplicate_keys_after_substitution(self):
        with pytest.raises(ValueError, match="duplicate"):
            resolve_schema('{"{{field}}":1,"text":2}', {"field": "text"})


class TestBuildResponseFormat:
    def test_shape_and_name_sanitized(self):
        payload = build_response_format(
            {"name": "My Set!", "json_schema": '{"type":"object"}'}, {}
        )
        assert payload["type"] == "json_schema"
        assert payload["json_schema"]["name"] == "My_Set_"
        assert payload["json_schema"]["strict"] is True
        assert payload["json_schema"]["schema"] == {"type": "object"}

    def test_accepts_sillytavern_wrapper(self):
        payload = build_response_format(
            {
                "name": "Row name",
                "json_schema": (
                    '{"name":"Continuation","strict":false,"description":"d",'
                    '"value":{"type":"object","properties":{"text":{"type":"string"}}}}'
                ),
            },
            {},
        )
        assert payload["json_schema"]["name"] == "Continuation"
        assert payload["json_schema"]["strict"] is False
        assert payload["json_schema"]["description"] == "d"
        assert payload["json_schema"]["schema"]["type"] == "object"
        assert "value" not in payload["json_schema"]["schema"]


class TestParseStructured:
    def test_parses_valid_json(self):
        assert parse_structured('{"a": 1}') == {"a": 1}

    def test_repairs_truncated_json(self):
        assert parse_structured('{"text": "hello') == {"text": "hello"}

    def test_rejects_non_json_prose(self):
        assert parse_structured("just prose") is None


class TestRender:
    def test_raw_and_escaped(self):
        assert render_structured('{"text":"<b>"}', "{{{text}}}", {}) == "<b>"
        assert render_structured('{"text":"<b>"}', "{{text}}", {}) == "&lt;b&gt;"

    def test_each_and_slice(self):
        raw = '[{"text":"a"},{"text":"b"},{"text":"c"}]'
        assert render_structured(raw, "{{#each (slice this 0 -1)}}{{{text}}}{{/each}}", {}) == "ab"

    def test_if_eq(self):
        raw = '{"type":"action","text":"run"}'
        out = render_structured(raw, '{{#if (eq type "action")}}*{{{text}}}*{{/if}}', {})
        assert out == "*run*"

    def test_string_helpers(self):
        raw = '{"text":"A1B2"}'
        assert render_structured(raw, "{{upper text}}", {}) == "A1B2"
        assert render_structured(raw, '{{replace text "/[0-9]+/g" "N"}}', {}) == "ANBN"
        assert render_structured(raw, '{{replace text "1" "X"}}', {}) == "AXB2"

    def test_macro_helper(self):
        out = render_structured('{"greeting":"Hi {{name}}"}', "{{macro greeting}}", {"name": "Bob"})
        assert out == "Hi Bob"


class TestValidators:
    def test_schema_validation(self):
        assert validate_schema_text('{"type":"object"}') is None
        assert validate_schema_text("{nope") is not None
        assert validate_schema_text("") is not None

    def test_template_validation(self):
        assert validate_template("{{{text}}}") is None
        assert validate_template("") is not None
