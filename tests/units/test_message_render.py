"""Unit tests for focus/core/message_render.py."""

import json

from focus.core.message_render import escape_html, render_message_segments


class TestRenderMessageSegments:
    def test_segments_json_fast_path(self):
        segments = [{"type": "text", "content": "hello"}]
        result = render_message_segments("ignored", None, json.dumps(segments))
        assert result == segments

    def test_invalid_segments_json_raises(self):
        # The fast path trusts stored data; a corrupt value is a loud failure.
        import pytest

        with pytest.raises(json.JSONDecodeError):
            render_message_segments("x", None, "{not json")

    def test_legacy_plain_text(self):
        assert render_message_segments("plain", None) == [{"type": "text", "content": "plain"}]

    def test_legacy_reasoning_from_variant_meta(self):
        meta = json.dumps({"reasoning": "  think & <care>  "})
        result = render_message_segments("answer", meta)
        assert result == [
            {"type": "reasoning", "html": "think &amp; &lt;care&gt;", "index": 0},
            {"type": "text", "content": "answer"},
        ]

    def test_legacy_malformed_meta_ignored(self):
        result = render_message_segments("answer", "{bad")
        assert result == [{"type": "text", "content": "answer"}]

    def test_legacy_no_reasoning_meta(self):
        result = render_message_segments("answer", json.dumps({"other": 1}))
        assert result == [{"type": "text", "content": "answer"}]

    def test_legacy_whitespace_reasoning_kept_as_empty_segment(self):
        result = render_message_segments("answer", json.dumps({"reasoning": "   "}))
        assert result == [
            {"type": "reasoning", "html": "", "index": 0},
            {"type": "text", "content": "answer"},
        ]


class TestEscapeHtml:
    def test_escapes_all_special_chars(self):
        assert escape_html('a&b<c>"d') == "a&amp;b&lt;c&gt;&quot;d"

    def test_plain_text_unchanged(self):
        assert escape_html("plain text") == "plain text"
