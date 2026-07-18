import pytest

from focus.routers.stream_utils import filter_unsupported_modalities, apply_claude_caching


class TestFilterUnsupportedModalities:
    def test_none_modalities_returns_unchanged(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert filter_unsupported_modalities(msgs, None) == msgs

    def test_all_modalities_supported(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert filter_unsupported_modalities(msgs, ["image", "audio"]) == msgs

    def test_removes_images_when_not_supported(self):
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": "hello"},
            {"type": "image_url", "image_url": {"url": "data:,"}},
        ]}]
        result = filter_unsupported_modalities(msgs, ["audio"])
        # Collapsed to plain string since only text remains
        assert result[0]["content"] == "hello"

    def test_collapses_single_text_to_string(self):
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": "just text"},
        ]}]
        result = filter_unsupported_modalities(msgs, ["audio"])
        assert result[0]["content"] == "just text"

    def test_removes_message_with_no_remaining_parts(self):
        msgs = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": "data:,"}},
        ]}]
        result = filter_unsupported_modalities(msgs, ["audio"])
        assert result == []

    def test_preserves_audio_when_supported(self):
        msgs = [{"role": "user", "content": [
            {"type": "text", "text": "desc"},
            {"type": "input_audio", "input_audio": {"data": "...", "format": "wav"}},
        ]}]
        result = filter_unsupported_modalities(msgs, ["audio"])
        assert len(result[0]["content"]) == 2

    def test_removes_audio_when_not_supported(self):
        msgs = [{"role": "user", "content": [
            {"type": "input_audio", "input_audio": {"data": "..."}},
        ]}]
        result = filter_unsupported_modalities(msgs, ["image"])
        assert result == []

    def test_string_content_passes_through(self):
        msgs = [{"role": "user", "content": "plain text"}]
        result = filter_unsupported_modalities(msgs, [])
        assert result == msgs


class TestApplyClaudeCaching:
    def test_disabled_returns_unchanged(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = apply_claude_caching(msgs, cache_enabled=False)
        assert result == msgs

    def test_empty_messages(self):
        assert apply_claude_caching([], cache_enabled=True) == []

    def test_injects_cache_on_greeting(self):
        msgs = [
            {"role": "assistant", "content": "greeting", "_greeting": True},
            {"role": "user", "content": "hi"},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True)
        assert "_greeting" not in result[0]
        assert "cache_control" in result[0]["content"][0]

    def test_injects_cache_on_fallback(self):
        msgs = [
            {"role": "assistant", "content": "first"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True, cache_depth=5)
        assert "cache_control" in result[0]["content"][0]

    def test_cleans_up_greeting_tag(self):
        msgs = [
            {"role": "assistant", "content": "hi", "_greeting": True},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True)
        assert "_greeting" not in result[0]

    def test_sliding_breakpoint(self):
        msgs = [
            {"role": "assistant", "content": "greeting", "_greeting": True},
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
            {"role": "assistant", "content": "d"},
            {"role": "user", "content": "e"},
            {"role": "assistant", "content": "f"},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True, cache_depth=2)
        # static on greeting (idx 0), sliding on idx 5 (len=7, cache_depth=2)
        assert "cache_control" in result[0]["content"][0]
        assert "cache_control" in result[5]["content"][0]
