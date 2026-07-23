import json

from focus.routers.stream_utils import (
    _append_history_with_tool_calls,
    apply_claude_caching,
    filter_unsupported_modalities,
)


class TestFilterUnsupportedModalities:
    def test_none_modalities_returns_unchanged(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert filter_unsupported_modalities(msgs, None) == msgs

    def test_all_modalities_supported(self):
        msgs = [{"role": "user", "content": "hello"}]
        assert filter_unsupported_modalities(msgs, ["image", "audio"]) == msgs

    def test_removes_images_when_not_supported(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hello"},
                    {"type": "image_url", "image_url": {"url": "data:,"}},
                ],
            }
        ]
        result = filter_unsupported_modalities(msgs, ["audio"])
        # Collapsed to plain string since only text remains
        assert result[0]["content"] == "hello"

    def test_collapses_single_text_to_string(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "just text"},
                ],
            }
        ]
        result = filter_unsupported_modalities(msgs, ["audio"])
        assert result[0]["content"] == "just text"

    def test_removes_message_with_no_remaining_parts(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": "data:,"}},
                ],
            }
        ]
        result = filter_unsupported_modalities(msgs, ["audio"])
        assert result == []

    def test_preserves_audio_when_supported(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "desc"},
                    {"type": "input_audio", "input_audio": {"data": "...", "format": "wav"}},
                ],
            }
        ]
        result = filter_unsupported_modalities(msgs, ["audio"])
        assert len(result[0]["content"]) == 2

    def test_removes_audio_when_not_supported(self):
        msgs = [
            {
                "role": "user",
                "content": [
                    {"type": "input_audio", "input_audio": {"data": "..."}},
                ],
            }
        ]
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

    def test_always_caches_messages_0(self):
        msgs = [
            {"role": "assistant", "content": "greeting", "_greeting": True},
            {"role": "user", "content": "hi"},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True)
        assert "_greeting" not in result[0]
        assert "cache_control" in result[0]["content"][0]
        assert "cache_control" not in result[1].get("content", {})

    def test_static_cache_without_sliding_when_too_shallow(self):
        msgs = [
            {"role": "system", "content": "system instructions"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True, cache_depth=5)
        # messages[0] always gets static cache
        assert "cache_control" in result[0]["content"][0]
        # only 1 user, not enough for sliding at depth=5
        assert "cache_control" not in result[1].get("content", {})
        assert "cache_control" not in result[2].get("content", {})

    def test_cleans_up_greeting_tag(self):
        msgs = [
            {"role": "assistant", "content": "hi", "_greeting": True},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True)
        assert "_greeting" not in result[0]
        assert "cache_control" in result[0]["content"][0]

    def test_sliding_breakpoint(self):
        msgs = [
            {"role": "system", "content": "system instructions"},
            {"role": "user", "content": "a"},  # 3rd user from end
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},  # 2nd user from end
            {"role": "assistant", "content": "d"},
            {"role": "user", "content": "e"},  # 1st user from end (current)
            {"role": "assistant", "content": "f"},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True, cache_depth=2)
        # static on messages[0], sliding on user "a" (idx 1)
        assert "cache_control" in result[0]["content"][0]
        assert "cache_control" in result[1]["content"][0]

    def test_sliding_uses_second_to_last_fallback(self):
        msgs = [
            {"role": "system", "content": "instructions"},
            {"role": "user", "content": "first msg"},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "second msg"},
            {"role": "assistant", "content": "done"},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True, cache_depth=5)
        # 2 users, not enough for cache_depth+1=6, but >1 so second-to-last user gets cache
        assert "cache_control" in result[0]["content"][0]
        assert "cache_control" in result[1]["content"][0]

    def test_no_sliding_when_only_one_user(self):
        msgs = [
            {"role": "system", "content": "instructions"},
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True, cache_depth=5)
        # only messages[0] gets static cache, no sliding
        assert "cache_control" in result[0]["content"][0]
        assert "cache_control" not in result[1].get("content", "")
        assert "cache_control" not in result[2].get("content", "")

    def test_strips_old_cache_control_and_readds_on_messages_0(self):
        msgs = [
            {
                "role": "system",
                "content": [
                    {
                        "type": "text",
                        "text": "instructions",
                        "cache_control": {"type": "ephemeral"},
                    },
                ],
            },
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "ok"},
        ]
        result = apply_claude_caching(msgs, cache_enabled=True)
        # Old cache_control stripped, new one added on messages[0]
        assert "cache_control" in result[0]["content"][0]


def _tc(tc_id, name="sd_image_gen", result="ok", extra=None):
    return {
        "id": tc_id,  # local uuid PK (NOT the provider call id)
        "tool_name": name,
        "arguments": "{}",
        "result": result,
        "extra_message_json": json.dumps(extra) if extra else None,
    }


def _seg_call(provider_id, name="sd_image_gen"):
    # Segments store the *provider* call id, which never matches tool_calls.id
    return {"id": provider_id, "type": "function",
            "function": {"name": name, "arguments": "{}"}}


def _row(segments=None, reasoning=None):
    return {
        "role": "assistant",
        "content": "pre-tool text\npost-tool reaction",
        "reasoning": reasoning,
        "variant_id": "v1",
        "segments_json": json.dumps(segments) if segments is not None else None,
    }


class TestAppendHistoryWithToolCalls:
    async def test_segments_split_preserves_generation_order(self):
        segments = [
            {"type": "reasoning", "html": "thinking &amp; stuff", "index": 0},
            {"type": "text", "content": "pre-tool text"},
            {"type": "tool_boundary", "tool_calls": [_seg_call("call_abc")]},
            {"type": "text", "content": "post-tool reaction"},
        ]
        extra = {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:,"}}]}
        tcs = [_tc("uuid-1", result="SUCCESS: image", extra=extra)]
        history = []
        await _append_history_with_tool_calls(history, _row(segments), {}, {"v1": tcs})

        assert [m["role"] for m in history] == ["assistant", "tool", "user", "assistant"]
        assert history[0]["content"] == "pre-tool text"
        assert history[0]["reasoning"] == "thinking & stuff"
        assert history[0]["tool_calls"][0]["id"] == "uuid-1"
        assert history[1]["tool_call_id"] == "uuid-1"
        assert history[1]["content"] == "SUCCESS: image"
        assert history[2] == extra
        assert history[3]["content"] == "post-tool reaction"
        assert "tool_calls" not in history[3]

    async def test_segments_multiple_tool_rounds(self):
        segments = [
            {"type": "text", "content": "first"},
            {"type": "tool_boundary", "tool_calls": [_seg_call("call_1")]},
            {"type": "text", "content": "second"},
            {"type": "tool_boundary", "tool_calls": [_seg_call("call_2")]},
            {"type": "text", "content": "third"},
        ]
        tcs = [_tc("uuid-1", result="r1"), _tc("uuid-2", result="r2")]
        history = []
        await _append_history_with_tool_calls(history, _row(segments), {}, {"v1": tcs})

        assert [m["role"] for m in history] == [
            "assistant", "tool", "assistant", "tool", "assistant",
        ]
        assert history[0]["content"] == "first"
        assert history[2]["content"] == "second"
        assert history[2]["tool_calls"][0]["id"] == "uuid-2"
        assert history[4]["content"] == "third"

    async def test_empty_final_chunk_skipped(self):
        segments = [
            {"type": "text", "content": "only text"},
            {"type": "tool_boundary", "tool_calls": [_seg_call("call_1")]},
        ]
        tcs = [_tc("uuid-1")]
        history = []
        await _append_history_with_tool_calls(history, _row(segments), {}, {"v1": tcs})

        assert [m["role"] for m in history] == ["assistant", "tool"]

    async def test_legacy_boundary_falls_back_to_single_entry(self):
        segments = [
            {"type": "text", "content": "pre"},
            {"type": "tool_boundary"},
            {"type": "text", "content": "post"},
        ]
        tcs = [_tc("uuid-1", result="res")]
        history = []
        await _append_history_with_tool_calls(history, _row(segments), {}, {"v1": tcs})

        assert [m["role"] for m in history] == ["assistant", "tool"]
        assert history[0]["tool_calls"][0]["id"] == "uuid-1"

    async def test_no_segments_falls_back_to_single_entry(self):
        tcs = [_tc("uuid-1", result="res")]
        history = []
        await _append_history_with_tool_calls(history, _row(None), {}, {"v1": tcs})

        assert [m["role"] for m in history] == ["assistant", "tool"]
        assert history[0]["content"] == "pre-tool text\npost-tool reaction"

    async def test_more_rows_than_segment_calls_are_ignored(self):
        # Partial save edge: tc rows without a matching boundary are not
        # emitted (a tool message without preceding tool_calls is invalid).
        segments = [
            {"type": "text", "content": "pre"},
            {"type": "tool_boundary", "tool_calls": [_seg_call("call_1")]},
            {"type": "text", "content": "post"},
        ]
        tcs = [_tc("uuid-1", result="r1"), _tc("uuid-2", result="orphan")]
        history = []
        await _append_history_with_tool_calls(history, _row(segments), {}, {"v1": tcs})

        assert [m["role"] for m in history] == ["assistant", "tool", "assistant"]
        assert history[1]["content"] == "r1"
        assert history[2]["content"] == "post"
