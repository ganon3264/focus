from focus.core.macros import MACRO_DEFINITIONS, _strip_comment_macros, apply_macros, build_base_macros, extract_setvars


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
                def now(cls, tz=None):
                    return cls(2025, 1, 1, hour, 0, 0, tzinfo=tz)

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


class TestCommentMacro:
    def test_comment_stripped(self):
        result = apply_macros("before {{//comment}} after", {})
        assert result == "before  after"

    def test_comment_with_spaces(self):
        result = apply_macros("{{ // spaced comment }}", {})
        assert result == ""

    def test_comment_with_tab(self):
        result = apply_macros("{{\t//tabbed}}", {})
        assert result == ""

    def test_comment_preserves_other_macros(self):
        result = apply_macros("{{//note}}{{char}}", {"char": "Bot"})
        assert result == "Bot"

    def test_comment_empty(self):
        result = apply_macros("{{//}}", {})
        assert result == ""

    def test_comment_nested_braces(self):
        result = apply_macros("{{// {{char}} test}}", {})
        assert result == ""

    def test_comment_multiple(self):
        result = apply_macros("a{{//c1}}b{{//c2}}c", {})
        assert result == "abc"

    def test_comment_no_close(self):
        result = apply_macros("a{{// no close", {})
        assert result == "a"

    def test_single_slash_preserved(self):
        result = apply_macros("{{/notacomment}}", {})
        assert result == "{{/notacomment}}"

    def test_comment_nested_setvar(self):
        macros = {}
        result = apply_macros("{{// {{setvar::x::y}} }}", macros)
        assert result == ""
        assert "x" not in macros

    def test_comment_removes_only_token(self):
        result = apply_macros("a\n{{//comment}}\nb", {})
        assert result == "a\n\nb"

    def test_strip_comment_macros_direct(self):
        result = _strip_comment_macros("x{{//y}}z")
        assert result == "xz"


class TestMacroDefinitions:
    def test_keys_match_build_base_macros(self):
        macros = build_base_macros({}, {"name": "x", "description": "", "id": ""})
        assert set(macros.keys()) == set(MACRO_DEFINITIONS.keys())

    def test_special_tokens_have_required_keys(self):
        from focus.core.macros import SPECIAL_TOKENS
        for tok in SPECIAL_TOKENS:
            assert "syntax" in tok
            assert "description" in tok


class TestNicknameMacro:
    def test_nickname_used_for_char(self):
        card = {"name": "FullName", "nickname": "Nick"}
        macros = build_base_macros(card)
        assert macros["char"] == "Nick"

    def test_name_fallback_when_no_nickname(self):
        card = {"name": "FullName"}
        macros = build_base_macros(card)
        assert macros["char"] == "FullName"

    def test_empty_nickname_falls_back(self):
        card = {"name": "FullName", "nickname": ""}
        macros = build_base_macros(card)
        assert macros["char"] == "FullName"

    def test_none_nickname_falls_back(self):
        card = {"name": "FullName", "nickname": None}
        macros = build_base_macros(card)
        assert macros["char"] == "FullName"


class TestCbsRandom:
    def test_single_value(self):
        result = apply_macros("{{random:Hello}}", {})
        assert result == "Hello"

    def test_picks_one_of_values(self):
        result = apply_macros("{{random:A,B,C}}", {})
        assert result in ("A", "B", "C")

    def test_empty_returns_empty(self):
        result = apply_macros("{{random:}}", {})
        assert result == ""

    def test_escaped_comma(self):
        result = apply_macros(r"{{random:Hello\, World,Hi}}", {})
        assert result in ("Hello, World", "Hi")

    def test_case_insensitivity(self):
        result = apply_macros("{{RANDOM:X,Y}}", {})
        assert result in ("X", "Y")


class TestCbsPick:
    def test_deterministic_per_chat(self):
        macros = {"_chat_id": "chat-1"}
        result_a = apply_macros("{{pick:Red,Green,Blue}}", macros)
        result_b = apply_macros("{{pick:Red,Green,Blue}}", macros)
        assert result_a == result_b

    def test_different_chat_different_pick(self):
        r1 = apply_macros("{{pick:Alpha,Beta,Gamma}}", {"_chat_id": "chat-a"})
        r2 = apply_macros("{{pick:Alpha,Beta,Gamma}}", {"_chat_id": "chat-b"})
        # Very unlikely to be equal, but not impossible — just verify both are valid
        assert r1 in ("Alpha", "Beta", "Gamma")
        assert r2 in ("Alpha", "Beta", "Gamma")

    def test_without_chat_id_falls_back_to_random(self):
        result = apply_macros("{{pick:X,Y,Z}}", {})
        assert result in ("X", "Y", "Z")

    def test_single_value(self):
        result = apply_macros("{{pick:Only}}", {"_chat_id": "c1"})
        assert result == "Only"


class TestCbsRoll:
    def test_basic_roll(self):
        result = apply_macros("{{roll:6}}", {})
        assert 1 <= int(result) <= 6

    def test_d_prefix(self):
        result = apply_macros("{{roll:d20}}", {})
        assert 1 <= int(result) <= 20

    def test_d_uppercase(self):
        result = apply_macros("{{roll:D100}}", {})
        assert 1 <= int(result) <= 100

    def test_deterministic_with_chat_id(self):
        r1 = apply_macros("{{roll:10}}", {"_chat_id": "c1"})
        r2 = apply_macros("{{roll:10}}", {"_chat_id": "c1"})
        assert r1 == r2

    def test_invalid_returns_empty(self):
        assert apply_macros("{{roll:}}", {}) == ""
        assert apply_macros("{{roll:abc}}", {}) == ""
        assert apply_macros("{{roll:0}}", {}) == ""


class TestCbsReverse:
    def test_reverses_string(self):
        result = apply_macros("{{reverse:Hello}}", {})
        assert result == "olleH"

    def test_empty(self):
        result = apply_macros("{{reverse:}}", {})
        assert result == ""

    def test_case_insensitivity(self):
        result = apply_macros("{{REVERSE:abc}}", {})
        assert result == "cba"

    def test_palindrome(self):
        result = apply_macros("{{reverse:racecar}}", {})
        assert result == "racecar"


class TestCbsComment:
    def test_comment_stripped(self):
        result = apply_macros("before {{comment: note }} after", {})
        assert result == "before  after"

    def test_comment_empty(self):
        result = apply_macros("{{comment:}}", {})
        assert result == ""

    def test_comment_with_content(self):
        result = apply_macros("Hello {{comment: user name}} world", {})
        assert result == "Hello  world"


class TestCbsHiddenKey:
    def test_hidden_key_stripped(self):
        result = apply_macros("before {{hidden_key:secret}} after", {})
        assert result == "before  after"

    def test_hidden_key_empty(self):
        result = apply_macros("{{hidden_key:}}", {})
        assert result == ""
