from __future__ import annotations

from focus.core.regex_scripts import (
    apply_to_display_messages,
    apply_to_prompt_history,
    preview_transform,
    validate_pattern,
)
from focus.prompt_chain import assemble_prompt


def _script(**kw) -> dict:
    base = {
        "pattern": "",
        "replacement": "",
        "flags": "",
        "placement": "ai",
        "apply_prompt": True,
        "apply_display": True,
        "as_block": False,
        "enabled": 1,
        "min_depth": 0,
        "max_depth": -1,
    }
    base.update(kw)
    return base


STRIP = _script(pattern=r"A beat\.\s*", replacement="")


class TestValidatePattern:
    def test_valid(self):
        assert validate_pattern(r"A beat\.", "") is None

    def test_invalid(self):
        assert validate_pattern("(", "") is not None

    def test_empty(self):
        assert validate_pattern("", "") is not None


class TestPromptApplication:
    async def test_ai_placement_leaves_user_alone(self):
        history = [
            {"role": "user", "content": "A beat. user"},
            {"role": "assistant", "content": "A beat. ai"},
        ]
        await apply_to_prompt_history(history, [STRIP])
        assert history[0]["content"] == "A beat. user"
        assert history[1]["content"] == "ai"

    async def test_reasoning_placement(self):
        history = [{"role": "assistant", "content": "x", "reasoning": "A beat. think"}]
        await apply_to_prompt_history(history, [_script(pattern=r"A beat\.\s*", replacement="", placement="reasoning")])
        assert history[0]["reasoning"] == "think"
        assert history[0]["content"] == "x"

    async def test_depth_window_relative_to_newest(self):
        history = [
            {"role": "assistant", "content": "A beat. old"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "A beat. new"},
        ]
        await apply_to_prompt_history(history, [_script(pattern=r"A beat\.\s*", replacement="", max_depth=0)])
        assert history[0]["content"] == "A beat. old"
        assert history[2]["content"] == "new"

    async def test_min_depth_skips_recent(self):
        history = [
            {"role": "assistant", "content": "A beat. old"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "A beat. new"},
        ]
        await apply_to_prompt_history(history, [_script(pattern=r"A beat\.\s*", replacement="", min_depth=2)])
        assert history[0]["content"] == "old"
        assert history[2]["content"] == "A beat. new"

    async def test_display_only_not_applied_to_prompt(self):
        history = [{"role": "assistant", "content": "A beat. x"}]
        await apply_to_prompt_history(
            history, [_script(pattern=r"A beat\.\s*", replacement="", apply_prompt=False)]
        )
        assert history[0]["content"] == "A beat. x"

    async def test_whitespace_pattern_is_not_a_draft(self):
        history = [{"role": "assistant", "content": "a b c"}]
        await apply_to_prompt_history(history, [_script(pattern=" ", replacement="")])
        assert history[0]["content"] == "abc"

    async def test_empty_pattern_never_applies(self):
        # An empty regex matches at every position; a draft must not splice the
        # replacement into the text.
        history = [{"role": "assistant", "content": "Hello world"}]
        await apply_to_prompt_history(history, [_script(pattern="", replacement="X")])
        assert history[0]["content"] == "Hello world"

    async def test_multimodal_text_parts_only(self):
        history = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "A beat. hi"},
                    {"type": "image_url", "image_url": {"url": "x"}},
                ],
            }
        ]
        await apply_to_prompt_history(history, [_script(pattern=r"A beat\.\s*", replacement="", placement="user")])
        assert history[0]["content"][0]["text"] == "hi"
        assert history[0]["content"][1]["type"] == "image_url"

    async def test_synthetic_tool_and_internal_ignored(self):
        history = [
            {"role": "assistant", "content": "A beat. x"},
            {"role": "tool", "content": "A beat. result"},
            {"role": "user", "content": "A beat. injected", "internal": True},
        ]
        await apply_to_prompt_history(history, [STRIP])
        assert history[0]["content"] == "x"
        assert history[1]["content"] == "A beat. result"
        assert history[2]["content"] == "A beat. injected"


class TestDisplayApplication:
    async def test_text_and_reasoning_segments(self):
        messages = [
            {
                "role": "assistant",
                "segments": [
                    {"type": "text", "content": "A beat. x"},
                    {"type": "reasoning", "html": "A beat. think"},
                ],
            }
        ]
        await apply_to_display_messages(
            messages,
            [
                _script(pattern=r"A beat\.\s*", replacement="", placement="ai"),
                _script(pattern=r"A beat\.\s*", replacement="", placement="reasoning"),
            ],
        )
        assert messages[0]["segments"][0]["content"] == "x"
        assert messages[0]["segments"][1]["html"] == "think"

    async def test_user_role_uses_user_placement(self):
        messages = [{"role": "user", "segments": [{"type": "text", "content": "A beat. hi"}]}]
        await apply_to_display_messages(
            messages, [_script(pattern=r"A beat\.\s*", replacement="", placement="user")]
        )
        assert messages[0]["segments"][0]["content"] == "hi"

    async def test_reasoning_html_is_escaped(self):
        messages = [
            {"role": "assistant", "segments": [{"type": "reasoning", "html": "A beat. a &lt; b"}]}
        ]
        await apply_to_display_messages(
            messages, [_script(pattern=r"A beat\.\s*", replacement="", placement="reasoning")]
        )
        assert messages[0]["segments"][0]["html"] == "a &lt; b"


class TestBlockApplication:
    async def test_block_splits_text_segment(self):
        messages = [{"role": "assistant", "segments": [{"type": "text", "content": "before <think>secret</think> after"}]}]
        await apply_to_display_messages(messages, [
            _script(name="Think", pattern=r"<think>(.*?)</think>", replacement="", as_block=True, flags="s"),
        ])
        segs = messages[0]["segments"]
        assert [s["type"] for s in segs] == ["text", "block", "text"]
        assert segs[1]["title"] == "Think"
        assert segs[1]["html"] == "secret"

    async def test_block_prompt_strips_match(self):
        history = [{"role": "assistant", "content": "before <think>secret</think> after"}]
        await apply_to_prompt_history(history, [
            _script(name="Think", pattern=r"<think>(.*?)</think>", replacement="", as_block=True, flags="s"),
        ])
        assert history[0]["content"] == "before  after"

    async def test_block_prompt_skipped_when_display_only(self):
        history = [{"role": "assistant", "content": "before <think>secret</think> after"}]
        await apply_to_prompt_history(history, [
            _script(name="Think", pattern=r"<think>(.*?)</think>", replacement="", as_block=True, apply_prompt=False, flags="s"),
        ])
        assert history[0]["content"] == "before <think>secret</think> after"

    async def test_block_prompt_uses_replacement(self):
        history = [{"role": "assistant", "content": "before <think>secret</think> after"}]
        await apply_to_prompt_history(history, [
            _script(name="Think", pattern=r"<think>(.*?)</think>", replacement="[thinking]", as_block=True, flags="s"),
        ])
        assert history[0]["content"] == "before [thinking] after"

    async def test_block_skipped_when_display_off(self):
        messages = [{"role": "assistant", "segments": [{"type": "text", "content": "before <think>x</think> after"}]}]
        await apply_to_display_messages(messages, [
            _script(name="Think", pattern=r"<think>(.*?)</think>", replacement="", as_block=True, apply_display=False, flags="s"),
        ])
        assert messages[0]["segments"] == [{"type": "text", "content": "before <think>x</think> after"}]

    async def test_block_capture_defaults_to_whole_match(self):
        messages = [{"role": "assistant", "segments": [{"type": "text", "content": "[x]"}]}]
        await apply_to_display_messages(messages, [
            _script(name="Note", pattern=r"\[.*?\]", replacement="", as_block=True),
        ])
        segs = messages[0]["segments"]
        assert [s["type"] for s in segs] == ["block"]
        assert segs[0]["html"] == "[x]"


class TestPreview:
    def test_block_preview_delimits(self):
        out = preview_transform(
            r"<think>(.*?)</think>", "", "s", "a<think>b</think>c", as_block=True, name="Think"
        )
        assert out == "a[Think]\nb\n[/Think]c"

    def test_text_preview_substitutes(self):
        assert preview_transform("a", "b", "", "a cat") == "b cbt"


class TestAssemblePromptIntegration:
    async def test_regex_runs_after_macros(self):
        history = [{"role": "assistant", "content": "Hello {{char}}"}]
        messages = await assemble_prompt(
            [],
            history,
            {"name": "Alice"},
            [],
            {"char": "Alice"},
            regex_scripts=[_script(pattern="Alice", replacement="Bob", placement="ai")],
        )
        assert messages[-1]["content"] == "Hello Bob"

    async def test_no_scripts_is_noop(self):
        history = [{"role": "assistant", "content": "Hello {{char}}"}]
        messages = await assemble_prompt([], history, {"name": "Alice"}, [], {"char": "Alice"})
        assert messages[-1]["content"] == "Hello Alice"
