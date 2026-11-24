import logging

from focus.core.macros import (
    MACRO_DEFINITIONS,
    _strip_comment_macros,
    apply_macros,
    build_base_macros,
    extract_setvars,
    resolve_template_macros,
)


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

    def test_value_with_nested_macro(self):
        macros = {}
        text = "{{setvar::pov::only for {{user}}'s body. Never {{user}}'s thoughts.}}"
        result = extract_setvars(text, macros)
        assert result == ""
        assert macros["pov"] == "only for {{user}}'s body. Never {{user}}'s thoughts."

    def test_empty_text(self):
        macros = {}
        result = extract_setvars("", macros)
        assert result == ""
        assert macros == {}

    def test_scoped_multiline_trimmed_and_dedented(self):
        macros = {}
        result = extract_setvars(
            "a\n{{ setvar backstory }}\n    line one\n    line two\n{{ /setvar }}\nb",
            macros,
        )
        assert result == "a\n\nb"
        assert macros["backstory"] == "line one\nline two"

    def test_scoped_preserve_flag_keeps_whitespace(self):
        macros = {}
        extract_setvars("{{ # setvar code }}\n  a\n    b\n{{ /setvar }}", macros)
        assert macros["code"] == "\n  a\n    b\n"

    def test_scoped_var_alias(self):
        macros = {}
        extract_setvars("{{ var k }}v{{ /var }}", macros)
        assert macros["k"] == "v"

    def test_scoped_key_is_trimmed(self):
        macros = {}
        extract_setvars("{{ setvar  spaced  }}v{{ /setvar }}", macros)
        assert macros["spaced"] == "v"

    def test_scoped_sillytavern_colon_form(self):
        """ST spells the scoped form `{{setvar::key}}...{{/setvar}}`."""
        macros = {}
        result = extract_setvars(
            "a {{setvar::backstory}}\n    one\n    two\n{{/setvar}} b", macros
        )
        assert result == "a  b"
        assert macros["backstory"] == "one\ntwo"

    def test_scoped_colon_form_does_not_eat_inline_value(self):
        macros = {}
        result = extract_setvars("{{setvar::k::v}}", macros)
        assert result == ""
        assert macros["k"] == "v"

    def test_colon_in_key_never_opens_a_scope(self):
        # `{{setvar::a::b}}` stays an inline assignment; the stray closer is
        # left for the unknown-macro pass rather than swallowing the body.
        macros = {}
        text = "{{setvar::a::b}}x{{/setvar}}"
        assert extract_setvars(text, macros) == "x{{/setvar}}"
        assert macros["a"] == "b"

    def test_scoped_malformed_without_closing_tag_left_alone(self):
        macros = {}
        text = "{{ setvar x }}no close"
        assert extract_setvars(text, macros) == text
        assert macros == {}

    def test_nested_macro_resolves_after_declaration(self):
        text = (
            "{{setvar::pov::only for {{user}}'s body. Never {{user}}'s thoughts.}}"
            "{{getvar::pov}}"
        )
        assert apply_macros(text, {"user": "Shou"}) == (
            "only for Shou's body. Never Shou's thoughts."
        )


class TestConditionals:
    """SillyTavern presets gate their module payloads on variable truthiness."""

    def test_truthy_branch(self):
        assert apply_macros("{{setvar::on::1}}{{if {{getvar::on}}}}YES{{/if}}", {}) == "YES"

    def test_unset_variable_is_false(self):
        assert apply_macros("{{if {{getvar::on}}}}YES{{/if}}", {}) == ""

    def test_emptied_variable_is_false(self):
        text = "{{setvar::on::x}}{{setvar::on::}}{{if {{getvar::on}}}}YES{{/if}}"
        assert apply_macros(text, {}) == ""

    def test_negation(self):
        assert apply_macros("{{if !{{getvar::hud}}}}no hud{{/if}}", {}) == "no hud"
        assert apply_macros("{{setvar::hud::1}}{{if !{{getvar::hud}}}}no hud{{/if}}", {}) == ""

    def test_else(self):
        assert apply_macros("{{if {{getvar::x}}}}A{{else}}B{{/if}}", {}) == "B"
        assert apply_macros("{{setvar::x::1}}{{if {{getvar::x}}}}A{{else}}B{{/if}}", {}) == "A"

    def test_nested_conditions(self):
        text = (
            "{{setvar::a::1}}out[{{if {{getvar::a}}}}"
            "{{if {{getvar::b}}}}in{{else}}not in{{/if}}]{{/if}}"
        )
        assert apply_macros(text, {}) == "out[not in]"

    def test_nested_condition_leaves_no_bracket_residue(self):
        text = "{{if {{getvar::a}}}}A{{/if}}"
        assert "}}" not in apply_macros(text, {})

    def test_unclosed_condition_drops_the_opener_only(self):
        assert apply_macros("{{if {{getvar::a}}}}dangling", {}) == "dangling"

    def test_body_is_trimmed_and_dedented(self):
        text = "{{setvar::a::1}}{{if {{getvar::a}}}}\n    one\n      two\n{{/if}}"
        assert apply_macros(text, {}) == "one\n  two"

    def test_hash_flag_preserves_the_body_verbatim(self):
        text = "{{setvar::a::1}}{{#if {{getvar::a}}}}\n   one\n     two\n{{/if}}"
        assert apply_macros(text, {}) == "\n   one\n     two\n"

    def test_st_falsy_list_verbatim(self):
        """ST's five falsy strings; anything else (even "none") is true."""
        for value in ("", "false", "0", "off", "no"):
            text = f"{{{{setvar::f::{value}}}}}{{{{if {{{{getvar::f}}}}}}}}T{{{{/if}}}}"
            assert apply_macros(text, {}) == "", value
        for value in ("1", "on", "yes", "none", "null"):
            text = f"{{{{setvar::t::{value}}}}}{{{{if {{{{getvar::t}}}}}}}}T{{{{/if}}}}"
            assert apply_macros(text, {}) == "T", value
        # Case-insensitive, like the rest of macro land.
        for value in ("False", "OFF", "No"):
            text = f"{{{{setvar::f::{value}}}}}{{{{if {{{{getvar::f}}}}}}}}T{{{{/if}}}}"
            assert apply_macros(text, {}) == "", value

    def test_bare_word_condition_resolves_a_macro(self):
        card = {"name": "Aria", "description": "A cartographer.", "scenario": ""}
        macros = build_base_macros(card, None)
        assert apply_macros("{{if description}}# Desc{{/if}}", macros) == "# Desc"
        assert apply_macros("{{if scenario}}# Scenario{{/if}}", macros) == ""
        assert apply_macros("{{if !scenario}}none{{/if}}", macros) == "none"

    def test_dropped_branch_runs_no_setvars(self):
        """Only the taken branch is evaluated — a gated payload must not leak."""
        text = (
            "{{setvar::on::}}{{if {{getvar::on}}}}"
            "{{setvar::payload::leaked}}{{/if}}[{{getvar::payload}}]"
        )
        macros = {}
        assert apply_macros(text, macros) == "[]"
        assert "payload" not in macros

    def test_condition_sees_setvars_earlier_in_the_same_text(self):
        text = "{{setvar::a::1}}{{if {{getvar::a}}}}seen{{/if}}"
        assert apply_macros(text, {}) == "seen"

    def test_multiline_body(self):
        text = "{{setvar::a::1}}{{if {{getvar::a}}}}\none\ntwo\n{{/if}}"
        assert apply_macros(text, {}) == "one\ntwo"

    def test_st_module_zeroing_shape(self):
        """The Sola preamble: zero every toggle, then gate payloads on them."""
        text = (
            "{{// zeroing}}{{trim}}\n"
            "{{setvar::opt_hud::}}{{setvar::no_hud::}}{{trim}}\n"
            "{{if {{getvar::opt_hud}}}}\nHUD PAYLOAD\n{{/if}}\n"
            "{{if !{{getvar::no_hud}}}}\ndefault hud\n{{/if}}\n"
        )
        resolved = apply_macros(text, {})
        assert "HUD PAYLOAD" not in resolved
        assert "default hud" in resolved

    def test_resolution_is_idempotent(self):
        text = "{{setvar::a::1}}{{if {{getvar::a}}}}A{{/if}}B"
        once = apply_macros(text, {})
        assert apply_macros(once, {}) == once


class TestUnknownMacros:
    def test_warns_once_per_key(self, caplog):
        """A bloated imported preset repeats its foreign macros; one line each."""
        text = "{{bogus}}{{bogus}}{{other}}{{other}}{{bogus}}"
        with caplog.at_level(logging.WARNING, logger="focus.macros"):
            apply_macros(text, {})
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 2

    def test_unclosed_condition_warns_once(self, caplog):
        text = "{{if {{getvar::a}}}}{{if {{getvar::b}}}}x"
        with caplog.at_level(logging.WARNING, logger="focus.macros"):
            apply_macros(text, {})
        warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warnings) == 1


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

    def test_unknown_key_stripped(self):
        result = apply_macros("{{unknown}}", {})
        assert result == ""

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

    def test_scoped_setvar_resolves_through_getvar(self):
        result = apply_macros(
            "{{setvar g}}\n  Hello {{char}}\n{{/setvar}}{{getvar::g}}", {"char": "Alice"}
        )
        assert result == "Hello Alice"

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

    def test_single_slash_stripped(self):
        result = apply_macros("{{/notacomment}}", {})
        assert result == ""

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

    def test_the_pick_is_seeded_by_the_chat(self):
        """Across many chats the choices must actually spread out — a constant
        seed would make every conversation pick the same value."""
        values = ("Alpha", "Beta", "Gamma", "Delta", "Epsilon")
        picks = {
            apply_macros("{{pick:Alpha,Beta,Gamma,Delta,Epsilon}}", {"_chat_id": f"chat-{i}"})
            for i in range(12)
        }
        assert picks <= set(values)
        assert len(picks) > 1, "the pick ignores its seed"

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


class TestResolveTemplateMacros:
    def test_resolves_known_macros(self):
        assert resolve_template_macros("{{char}}", {"char": "Alice"}) == "Alice"
        assert resolve_template_macros("{{{char}}}", {"char": "Alice"}) == "Alice"

    def test_leaves_handlebars_paths_untouched(self):
        assert resolve_template_macros("{{text}}", {"char": "Alice"}) == "{{text}}"
        assert (
            resolve_template_macros("{{{json obj}}}", {"char": "Alice"})
            == "{{{json obj}}}"
        )

    def test_leaves_block_helpers_and_macro_helper_untouched(self):
        macros = {"char": "Alice"}
        template = "{{#each items}}{{text}} {{char}}{{/each}}"
        assert (
            resolve_template_macros(template, macros)
            == "{{#each items}}{{text}} Alice{{/each}}"
        )
        assert (
            resolve_template_macros('{{macro "{{char}}"}}', macros)
            == '{{macro "{{char}}"}}'
        )

    def test_triple_braces_raw_double_escaped(self):
        assert resolve_template_macros("{{{char}}}", {"char": "A&B"}) == "A&B"
        assert resolve_template_macros("{{char}}", {"char": "A&B"}) == "A&amp;B"

    def test_cbs_and_setvars(self):
        assert (
            resolve_template_macros("{{{getvar::prefill}}}", {"prefill": "x"})
            == "x"
        )
        macros: dict = {}
        out = resolve_template_macros("{{setvar::greeting::hi}} {{{getvar::greeting}}}", macros)
        assert out == " hi"
        assert macros["greeting"] == "hi"

    def test_unknown_getvar_resolves_empty(self):
        assert resolve_template_macros("{{{getvar::missing}}}", {}) == ""

    def test_scoped_setvar_can_hold_template_fragment(self):
        macros: dict = {}
        out = resolve_template_macros(
            "{{setvar frag}}\n *{{{text}}}*\n{{/setvar}}{{getvar::frag}}", macros
        )
        assert out == "*{{{text}}}*"
        assert macros["frag"] == "*{{{text}}}*"



