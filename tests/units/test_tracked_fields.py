from focus.core.tracked_fields import get_field, merge_delta


class TestMergeReasoningDetails:
    def test_accumulates_text_across_chunks(self):
        store: dict = {}
        merge_delta(store, "reasoning_details", [
            {"type": "reasoning.text", "text": "Hello ", "format": "unknown", "index": 0},
        ])
        merge_delta(store, "reasoning_details", [
            {"type": "reasoning.text", "text": "world", "format": "unknown", "index": 0},
        ])
        assert get_field(store, "reasoning_details") == [
            {"type": "reasoning.text", "text": "Hello world", "format": "unknown", "index": 0},
        ]

    def test_accumulates_summary_across_chunks(self):
        store: dict = {}
        item = {"type": "reasoning.summary", "format": "openai-responses-v1", "index": 0, "id": "rs_1"}
        merge_delta(store, "reasoning_details", [{**item, "summary": "Part one. "}])
        merge_delta(store, "reasoning_details", [{**item, "summary": "Part two."}])
        result = get_field(store, "reasoning_details")
        assert result[0]["summary"] == "Part one. Part two."
        assert result[0]["type"] == "reasoning.summary"
        assert result[0]["id"] == "rs_1"

    def test_signature_overwrites_while_text_accumulates(self):
        store: dict = {}
        merge_delta(store, "reasoning_details", [
            {"type": "reasoning.text", "text": "a", "signature": "old", "index": 0},
        ])
        merge_delta(store, "reasoning_details", [
            {"type": "reasoning.text", "text": "b", "signature": "new", "index": 0},
        ])
        result = get_field(store, "reasoning_details")
        assert result[0]["text"] == "ab"
        assert result[0]["signature"] == "new"

    def test_separate_indices_stay_separate(self):
        store: dict = {}
        merge_delta(store, "reasoning_details", [
            {"type": "reasoning.text", "text": "first", "index": 1},
        ])
        merge_delta(store, "reasoning_details", [
            {"type": "reasoning.text", "text": "second", "index": 0},
        ])
        assert [d["text"] for d in get_field(store, "reasoning_details")] == ["second", "first"]


class TestMergeAppendField:
    def test_reasoning_appends_chunks(self):
        store: list = []
        merge_delta(store, "reasoning", "think ")
        merge_delta(store, "reasoning", "more")
        assert get_field(store, "reasoning") == "think more"
