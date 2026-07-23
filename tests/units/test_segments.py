"""Tests for focus/core/segments.py — build_segments()."""

from focus.core.segments import build_segments


class TestBuildSegments:
    def test_text_only_single_iteration(self):
        result = build_segments(
            text_slices=[4],
            reasoning_slices=[0],
            final_text=["hello", " ", "world", "!"],
            final_reasoning=[],
        )
        assert result == [
            {"type": "text", "content": "hello world!"},
        ]

    def test_reasoning_only_single_iteration(self):
        result = build_segments(
            text_slices=[0],
            reasoning_slices=[2],
            final_text=[],
            final_reasoning=["deep ", "thought"],
        )
        assert len(result) == 1
        assert result[0]["type"] == "reasoning"
        assert result[0]["html"] == "deep thought"
        assert result[0]["index"] == 0

    def test_text_and_reasoning_in_same_iteration(self):
        result = build_segments(
            text_slices=[2],
            reasoning_slices=[1],
            final_text=["answer: ", "42"],
            final_reasoning=["calculating..."],
        )
        assert result == [
            {"type": "reasoning", "html": "calculating...", "index": 0},
            {"type": "text", "content": "answer: 42"},
        ]

    def test_tool_boundary_between_iterations(self):
        result = build_segments(
            text_slices=[2, 4],
            reasoning_slices=[0, 0],
            final_text=["pre", "-tool", "post", "-reaction"],
            final_reasoning=[],
        )
        assert result == [
            {"type": "text", "content": "pre-tool"},
            {"type": "tool_boundary"},
            {"type": "text", "content": "post-reaction"},
        ]

    def test_tool_boundary_with_tool_calls(self):
        tool_calls = [
            [{"id": "call_1", "type": "function", "function": {"name": "search", "arguments": "{}"}}],
        ]
        result = build_segments(
            text_slices=[1, 2],
            reasoning_slices=[0, 0],
            final_text=["querying...", "found result"],
            final_reasoning=[],
            tool_call_groups=tool_calls,
        )
        assert result == [
            {"type": "text", "content": "querying..."},
            {"type": "tool_boundary", "tool_calls": tool_calls[0]},
            {"type": "text", "content": "found result"},
        ]

    def test_multiple_tool_rounds(self):
        tool_calls = [
            [{"id": "call_a", "type": "function", "function": {"name": "search", "arguments": "{}"}}],
            [{"id": "call_b", "type": "function", "function": {"name": "read", "arguments": "{}"}}],
        ]
        result = build_segments(
            text_slices=[1, 2, 3],
            reasoning_slices=[0, 0, 0],
            final_text=["first", "second", "third"],
            final_reasoning=[],
            tool_call_groups=tool_calls,
        )
        assert result == [
            {"type": "text", "content": "first"},
            {"type": "tool_boundary", "tool_calls": tool_calls[0]},
            {"type": "text", "content": "second"},
            {"type": "tool_boundary", "tool_calls": tool_calls[1]},
            {"type": "text", "content": "third"},
        ]

    def test_legacy_tool_boundary_no_calls(self):
        """Without tool_call_groups, boundaries are plain markers."""
        result = build_segments(
            text_slices=[1, 2],
            reasoning_slices=[0, 0],
            final_text=["before", "after"],
            final_reasoning=[],
        )
        assert result == [
            {"type": "text", "content": "before"},
            {"type": "tool_boundary"},
            {"type": "text", "content": "after"},
        ]

    def test_empty_text_skips_text_segment(self):
        result = build_segments(
            text_slices=[1, 1],
            reasoning_slices=[0, 0],
            final_text=["only"],
            final_reasoning=[],
        )
        assert result == [
            {"type": "text", "content": "only"},
            # Iteration 1 has no new text (t_end == prev_t) but
            # the boundary from iteration 0 is still emitted
            {"type": "tool_boundary"},
        ]

    def test_empty_reasoning_skips_reasoning_segment(self):
        result = build_segments(
            text_slices=[1],
            reasoning_slices=[0],
            final_text=["hello"],
            final_reasoning=[],
        )
        assert result == [
            {"type": "text", "content": "hello"},
        ]

    def test_multiple_reasoning_segments(self):
        """Reasoning and text from iteration 0 appear before the boundary;
        iteration 1 adds more reasoning with no new text."""
        result = build_segments(
            text_slices=[1, 1],
            reasoning_slices=[2, 3],
            final_text=["done"],
            final_reasoning=["first ", "thought", "second thought"],
        )
        assert result == [
            {"type": "reasoning", "html": "first thought", "index": 0},
            {"type": "text", "content": "done"},
            {"type": "tool_boundary"},
            {"type": "reasoning", "html": "second thought", "index": 1},
        ]

    def test_whitespace_only_reasoning_is_skipped(self):
        result = build_segments(
            text_slices=[1],
            reasoning_slices=[2],
            final_text=["hello"],
            final_reasoning=[" ", "\t"],
        )
        assert result == [
            {"type": "text", "content": "hello"},
        ]

    def test_html_escaping_in_reasoning(self):
        result = build_segments(
            text_slices=[1],
            reasoning_slices=[1],
            final_text=["done"],
            final_reasoning=["x < 5 && y > 2"],
        )
        assert result[0]["html"] == "x &lt; 5 &amp;&amp; y &gt; 2"

    def test_no_iterations_returns_empty(self):
        result = build_segments(
            text_slices=[],
            reasoning_slices=[],
            final_text=[],
            final_reasoning=[],
        )
        assert result == []
