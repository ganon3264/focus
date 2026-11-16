"""Message search: the query text and the snippet a hit renders."""


class TestMatchQuery:
    def test_tokens_are_quoted_prefixes(self):
        from focus.core.search import match_query

        assert match_query("rain rust") == '"rain"* "rust"*'
        assert match_query("  rusty  ") == '"rusty"*'

    def test_punctuation_and_operators_are_text(self):
        from focus.core.search import match_query

        # A stray quote, star or keyword must not reach the FTS5 parser.
        assert match_query('percent"* OR') == '"percent"* "OR"*'
        assert match_query("well-known") == '"well"* "known"*'

    def test_nothing_to_search(self):
        from focus.core.search import match_query

        assert match_query("") == ""
        assert match_query("   ...  ") == ""
        # Punctuation that survives the split is a phrase of no terms: FTS5
        # finds nothing in it, so it is not a query at all.
        assert match_query("_") == ""
        assert match_query("’") == ""


class TestRenderSnippet:
    def test_marks_survive_the_tag_strip(self):
        from focus.core.search import MARK_CLOSE, MARK_OPEN, render_snippet

        raw = f'she said <span class="x">the {MARK_OPEN}rain{MARK_CLOSE}</span> falls'
        out = render_snippet(raw)

        assert out == "she said the <mark>rain</mark> falls"
        assert "<span" not in out

    def test_flattens_to_one_escaped_line(self):
        from focus.core.search import MARK_CLOSE, MARK_OPEN, render_snippet

        raw = f"a\n\nb  3 < 4 {MARK_OPEN}c{MARK_CLOSE}"
        assert render_snippet(raw) == "a b 3 &lt; 4 <mark>c</mark>"

    def test_caps_a_long_line_without_splitting_a_mark(self):
        from focus.core.search import MARK_CLOSE, MARK_OPEN, SNIPPET_CHARS, render_snippet

        raw = "x" * (SNIPPET_CHARS - 1) + MARK_OPEN + "y" * 40 + MARK_CLOSE
        out = render_snippet(raw)

        assert out.endswith("…")
        assert out.count("<mark>") == out.count("</mark>")
        # The cap counts the text, not the tags that mark it up.
        assert len(out.replace("<mark>", "").replace("</mark>", "")) <= SNIPPET_CHARS + 1
