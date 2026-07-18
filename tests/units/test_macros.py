from focus.core.macros import apply_macros, build_base_macros, extract_setvars


class TestBuildBaseMacros:
    def test_full_card_and_persona(self):
        card = {
            "name": "Sylvie",
            "description": "A fox",
            "personality": "Curious",
            "scenario": "Forest",
            "mes_example": "Hello",
        }
        persona = {"name": "Alex", "description": "A human", "id": "p1"}
        macros = build_base_macros(card, persona)
        assert macros["char"] == "Sylvie"
        assert macros["user"] == "Alex"
        assert macros["persona"] == "A human"
        assert macros["persona_id"] == "p1"
        assert macros["description"] == "A fox"
        assert macros["personality"] == "Curious"
        assert macros["scenario"] == "Forest"
        assert macros["mes_example"] == "Hello"

    def test_empty_card_returns_defaults(self):
        macros = build_base_macros({})
        assert macros["char"] == "Assistant"
        assert macros["user"] == "User"
        assert macros["persona"] == ""

    def test_no_persona_uses_fallbacks(self):
        macros = build_base_macros({"name": "Bot"}, None)
        assert macros["user"] == "User"
        assert macros["persona"] == ""

    def test_time_of_day_classification(self, monkeypatch):
        from datetime import datetime

        import focus.core.macros as m

        test_cases = [
            (6, "morning"),
            (11, "morning"),
            (12, "afternoon"),
            (16, "afternoon"),
            (17, "evening"),
            (20, "evening"),
            (21, "night"),
            (3, "night"),
        ]

        for hour, expected in test_cases:

            class FakeDatetime(datetime):
                @classmethod
                def now(cls):
                    return cls(2025, 1, 1, hour, 0, 0)

            monkeypatch.setattr(m, "datetime", FakeDatetime)
            macros = build_base_macros({})
            assert macros["time_of_day"] == expected, f"hour={hour} expected={expected} got={macros['time_of_day']}"

    def test_time_date_keys_present(self):
        macros = build_base_macros({})
        assert "time" in macros
        assert "date" in macros
        assert "weekday" in macros
        assert ":" in macros["time"]
        assert "-" in macros["date"]


class TestExtractSetvars:
    def test_extract_key_value(self):
        macros = {}
        result = extract_setvars("before {{setvar::key::value}} after", macros)
        assert result == "before  after"
        assert macros["key"] == "value"

    def test_var_alias(self):
        macros = {}
        result = extract_setvars("{{var::k::v}}", macros)
        assert result == ""
        assert macros["k"] == "v"

    def test_case_insensitivity(self):
        macros = {}
        result = extract_setvars("{{SETVAR::key::val}}", macros)
        assert result == ""
        assert macros["key"] == "val"

    def test_multiple_setvars(self):
        macros = {}
        result = extract_setvars("a={{var::a::1}} b={{setvar::b::2}}", macros)
        assert result == "a= b="
        assert macros["a"] == "1"
        assert macros["b"] == "2"

    def test_empty_text(self):
        macros = {}
        result = extract_setvars("", macros)
        assert result == ""
        assert macros == {}


class TestApplyMacros:
    def test_simple_substitution(self):
        result = apply_macros("Hello {{name}}", {"name": "World"})
        assert result == "Hello World"

    def test_getvar_prefix(self):
        result = apply_macros("Hi {{getvar::name}}", {"name": "Bob"})
        assert result == "Hi Bob"

    def test_getvar_missing_returns_empty(self):
        result = apply_macros("{{getvar::missing}}", {})
        assert result == ""

    def test_unknown_key_preserved(self):
        result = apply_macros("{{unknown}}", {})
        assert result == "{{unknown}}"

    def test_chain_resolution(self):
        macros = {"a": "Hello {{b}}", "b": "World"}
        result = apply_macros("{{a}}", macros)
        assert result == "Hello World"

    def test_trim_removes_blank_line(self):
        result = apply_macros("a\n{{trim}}\nb", {})
        assert result == "a\nb"

    def test_trim_with_variables(self):
        result = apply_macros("{{greeting}}\n{{trim}}\n{{name}}", {"greeting": "Hi", "name": "You"})
        assert result == "Hi\nYou"

    def test_trim_collapses_excess_newlines(self):
        result = apply_macros("a\n\n\n\n\nb\n{{trim}}", {})
        assert result == "a\n\nb"

    def test_trim_case_insensitive(self):
        result = apply_macros("x\n{{TRIM}}\ny", {})
        assert result == "x\ny"
        result = apply_macros("x\n{{Trim}}\ny", {})
        assert result == "x\ny"

    def test_trim_strips_leading_trailing(self):
        result = apply_macros("  \n{{trim}}\n  content\n  ", {})
        assert result == "content"

    def test_empty_text_returns_empty(self):
        result = apply_macros("", {})
        assert result == ""

    def test_max_passes_prevents_infinite_loop(self, monkeypatch):
        import focus.core.macros as m

        monkeypatch.setattr(m, "MACRO_MAX_PASSES", 2)
        macros = {"a": "{{a}}"}
        result = apply_macros("{{a}}", macros, 2)
        assert result == "{{a}}"

    def test_setvar_in_text(self):
        macros = {}
        result = apply_macros("{{setvar::greet::Hi}} {{greet}}", macros)
        assert result == " Hi"
        assert macros["greet"] == "Hi"

    def test_multiple_keys_same_line(self):
        result = apply_macros("{{a}} {{b}} {{c}}", {"a": "x", "b": "y", "c": "z"})
        assert result == "x y z"

    def test_no_macros_returns_original(self):
        result = apply_macros("plain text with no macros", {})
        assert result == "plain text with no macros"
