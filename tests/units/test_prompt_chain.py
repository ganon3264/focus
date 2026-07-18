from focus.prompt_chain import (
    _build_content,
    _merge_consecutive,
    partition_blocks,
    resolve_variable_blocks,
)


class TestBuildContent:
    """Tests for _build_content with {{media::x}} markers."""

    def _mock_load_media(self, media_row):
        return {
            "type": "image_url",
            "image_url": {"url": f"data:{media_row['mime_type']};base64,{media_row['id']}"},
        }

    def test_no_images_returns_plain_text(self, monkeypatch):
        monkeypatch.setattr("focus.prompt_chain._load_media", self._mock_load_media)
        result = _build_content("hello", [])
        assert result == "hello"

    def test_no_marker_appends_all_images(self, monkeypatch):
        monkeypatch.setattr("focus.prompt_chain._load_media", self._mock_load_media)
        images = [
            {"id": "img1", "image_path": "/fake/1.png", "mime_type": "image/png"},
            {"id": "img2", "image_path": "/fake/2.png", "mime_type": "image/png"},
        ]
        result = _build_content("hello", images)
        assert isinstance(result, list)
        assert len(result) == 3
        assert result[0] == {"type": "text", "text": "hello"}
        assert result[1]["image_url"]["url"].endswith("img1")
        assert result[2]["image_url"]["url"].endswith("img2")

    def test_marker_inserts_image_at_position(self, monkeypatch):
        monkeypatch.setattr("focus.prompt_chain._load_media", self._mock_load_media)
        images = [
            {"id": "imgA", "image_path": "/fake/a.png", "mime_type": "image/png"},
            {"id": "imgB", "image_path": "/fake/b.png", "mime_type": "image/png"},
        ]
        result = _build_content("cat: {{media::1}} and dog: {{media::2}}", images)
        assert len(result) == 4
        assert result[0] == {"type": "text", "text": "cat: "}
        assert result[1]["image_url"]["url"].endswith("imgA")
        assert result[2] == {"type": "text", "text": " and dog: "}
        assert result[3]["image_url"]["url"].endswith("imgB")

    def test_marker_at_start_and_end(self, monkeypatch):
        monkeypatch.setattr("focus.prompt_chain._load_media", self._mock_load_media)
        images = [{"id": "img", "image_path": "/fake/x.png", "mime_type": "image/png"}]
        result = _build_content("{{media::1}}middle{{media::1}}", images)
        assert len(result) == 3
        assert result[0]["image_url"]["url"].endswith("img")
        assert result[1] == {"type": "text", "text": "middle"}
        assert result[2]["image_url"]["url"].endswith("img")

    def test_out_of_range_left_as_raw_text(self, monkeypatch):
        monkeypatch.setattr("focus.prompt_chain._load_media", self._mock_load_media)
        images = [{"id": "img", "image_path": "/fake/x.png", "mime_type": "image/png"}]
        result = _build_content("a {{media::2}} b", images)
        assert len(result) == 3
        assert result[0] == {"type": "text", "text": "a "}
        assert result[1] == {"type": "text", "text": "{{media::2}}"}
        assert result[2] == {"type": "text", "text": " b"}

    def test_out_of_range_zero_left_as_raw_text(self, monkeypatch):
        monkeypatch.setattr("focus.prompt_chain._load_media", self._mock_load_media)
        images = [{"id": "img", "image_path": "/fake/x.png", "mime_type": "image/png"}]
        result = _build_content("{{media::0}}", images)
        assert len(result) == 1
        assert result[0] == {"type": "text", "text": "{{media::0}}"}

    def test_mixed_valid_and_invalid_markers(self, monkeypatch):
        monkeypatch.setattr("focus.prompt_chain._load_media", self._mock_load_media)
        images = [
            {"id": "img1", "image_path": "/fake/1.png", "mime_type": "image/png"},
            {"id": "img2", "image_path": "/fake/2.png", "mime_type": "image/png"},
        ]
        result = _build_content("{{media::1}} ok {{media::3}} bad {{media::2}}", images)
        assert len(result) == 5
        assert result[0]["image_url"]["url"].endswith("img1")
        assert result[1] == {"type": "text", "text": " ok "}
        assert result[2] == {"type": "text", "text": "{{media::3}}"}
        assert result[3] == {"type": "text", "text": " bad "}
        assert result[4]["image_url"]["url"].endswith("img2")

    def test_no_markers_no_images_returns_text(self, monkeypatch):
        monkeypatch.setattr("focus.prompt_chain._load_media", self._mock_load_media)
        result = _build_content("just text", [])
        assert result == "just text"

    def test_empty_text_with_images_no_markers(self, monkeypatch):
        monkeypatch.setattr("focus.prompt_chain._load_media", self._mock_load_media)
        images = [{"id": "img", "image_path": "/fake/x.png", "mime_type": "image/png"}]
        result = _build_content("", images)
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["image_url"]["url"].endswith("img")

    def test_media_marker_preserved_by_apply_macros(self):
        """Verify apply_macros does not strip {{media::x}} markers."""
        from focus.core.macros import apply_macros
        result = apply_macros("before {{media::2}} after", {})
        assert result == "before {{media::2}} after"


class TestMergeConsecutive:
    def test_same_role_merged(self):
        msgs = [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]
        result = _merge_consecutive(msgs)
        assert len(result) == 1
        assert result[0]["content"] == "a\nb"

    def test_different_roles_not_merged(self):
        msgs = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        result = _merge_consecutive(msgs)
        assert len(result) == 2

    def test_three_consecutive_same_role(self):
        msgs = [
            {"role": "user", "content": "a"},
            {"role": "user", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        result = _merge_consecutive(msgs)
        assert len(result) == 1
        assert result[0]["content"] == "a\nb\nc"

    def test_empty_input(self):
        assert _merge_consecutive([]) == []

    def test_single_message(self):
        msgs = [{"role": "user", "content": "hello"}]
        result = _merge_consecutive(msgs)
        assert len(result) == 1
        assert result[0]["content"] == "hello"

    def test_extra_metadata_preserved(self):
        msgs = [
            {"role": "user", "content": "a", "extra": "x"},
            {"role": "user", "content": "b", "extra": "y"},
        ]
        result = _merge_consecutive(msgs)
        assert result[0]["extra"] == "y"

    def test_image_content_parts(self):
        msgs = [
            {"role": "user", "content": [{"type": "text", "text": "a"}]},
            {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:,"}}]},
        ]
        result = _merge_consecutive(msgs)
        assert len(result) == 1
        assert len(result[0]["content"]) == 2

    def test_alternating_roles(self):
        msgs = [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]
        result = _merge_consecutive(msgs)
        assert len(result) == 3


class TestPartitionBlocks:
    def test_separates_variable_blocks(self):
        blocks = [
            {"name": "text1", "block_type": "text"},
            {"name": "var1", "block_type": "variable"},
            {"name": "text2", "block_type": "text"},
        ]
        var_blocks, regular_blocks, var_groups = partition_blocks(blocks)
        assert len(var_blocks) == 1
        assert len(regular_blocks) == 2

    def test_empty_blocks(self):
        var_blocks, regular_blocks, var_groups = partition_blocks([])
        assert var_blocks == []
        assert regular_blocks == []
        assert var_groups == {}

    def test_groups_by_variable_name(self):
        blocks = [
            {"name": "group1:opt1", "block_type": "variable"},
            {"name": "group1:opt2", "block_type": "variable"},
            {"name": "group2:opt1", "block_type": "variable"},
        ]
        _, _, var_groups = partition_blocks(blocks)
        assert len(var_groups["group1"]) == 2
        assert len(var_groups["group2"]) == 1

    def test_regular_blocks_only(self):
        blocks = [{"name": "t1", "block_type": "text"}, {"name": "t2", "block_type": "text"}]
        var_blocks, regular_blocks, var_groups = partition_blocks(blocks)
        assert var_blocks == []
        assert len(regular_blocks) == 2
        assert var_groups == {}


class TestResolveVariableBlocks:
    def test_resolves_simple_variable(self):
        macros = {"user": "World"}
        blocks = [{"name": "greeting", "content": "Hello {{user}}"}]
        resolve_variable_blocks(blocks, macros)
        assert macros["greeting"] == "Hello World"

    def test_empty_blocks_does_nothing(self):
        macros = {}
        resolve_variable_blocks([], macros)
        assert macros == {}

    def test_chained_variables(self):
        macros = {"base": "World"}
        blocks = [
            {"name": "a", "content": "Hello {{b}}"},
            {"name": "b", "content": "{{base}}!"},
        ]
        resolve_variable_blocks(blocks, macros)
        assert macros["a"] == "Hello World!"
        assert macros["b"] == "World!"

    def test_content_is_stripped(self):
        macros = {}
        blocks = [{"name": "x", "content": "  hello  "}]
        resolve_variable_blocks(blocks, macros)
        assert macros["x"] == "hello"
