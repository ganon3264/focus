import pytest

from focus.prompt_chain import (
    _merge_consecutive,
    partition_blocks,
    resolve_variable_blocks,
)


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
