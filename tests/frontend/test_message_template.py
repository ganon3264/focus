"""Tests for the chat/message.html template reasoning button.

Verifies that the server-rendered "Reasoning" button carries the
`data-ui="reasoning-toggle-btn"` hook so the client-side
`syncReasoningButtons` helper can find it without depending on a class
name (it must be hidden while a new stream is in progress and shown only
once `details.reasoning` is in the content).
"""

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

TEMPLATES_DIR = Path("templates").resolve()
PARTIALS_DIR = Path("partials").resolve()

loader = FileSystemLoader([str(TEMPLATES_DIR), str(PARTIALS_DIR)])
env = Environment(loader=loader, undefined=StrictUndefined)


def _render_message(message=None, **overrides):
    """Render chat/message.html with a minimal, well-formed message dict."""
    base = {
        "id": "m1",
        "role": "assistant",
        "position": 1,
        "active_index": 0,
        "variant_count": 1,
        "content": "Hello world",
        "model_name": "test-model",
        "created_at": "2024-01-01T00:00:00+00:00",
        "attachments": [],
    }
    if message:
        base.update(message)
    base.update(overrides)

    character = {"name": "Assistant", "image_path": None}
    persona = {"name": "User", "avatar_path": None}

    template = env.get_template("chat/message.html")
    return template.render(
        message=base,
        character=character,
        persona=persona,
        is_latest=True,
        msg_index=1,
        chat_id="c1",
    )


def _extract_reasoning_button(html: str) -> str:
    """Return the <button> tag for the reasoning toggle, or '' if missing."""
    match = re.search(r'<button[^>]*aria-label="Toggle reasoning"[^>]*>', html)
    return match.group(0) if match else ""


REASONING_SEGMENTS = [
    {"type": "reasoning", "index": 0, "html": "think"},
    {"type": "text", "content": "answer"},
]


def test_reasoning_button_present_when_message_has_reasoning():
    """Server should render the button when a reasoning block is on the page."""
    html = _render_message({"reasoning": "hidden reasoning", "segments": REASONING_SEGMENTS})
    btn = _extract_reasoning_button(html)
    assert btn, "Expected reasoning button to be rendered"
    assert 'data-ui="reasoning-toggle-btn"' in btn, (
        f"Reasoning button must carry data-ui=\"reasoning-toggle-btn\" so "
        f"syncReasoningButtons() can manage it. Got: {btn}"
    )


def test_reasoning_button_absent_when_no_reasoning():
    """No button when content has no <think> tags."""
    html = _render_message({"content": "plain text response"})
    assert _extract_reasoning_button(html) == ""


def test_reasoning_button_lives_on_the_rail():
    """The pre-answer reasoning block has no head of its own — the rail's toggle
    controls it, so the block leaves nothing behind while it is collapsed."""
    html = _render_message({"reasoning": "hidden", "segments": REASONING_SEGMENTS})
    meta = re.search(r'<div class="row-meta message-meta".*?</div>', html, re.S).group(0)
    assert "reasoning-toggle-btn" in meta, meta


def test_reasoning_button_absent_for_user_messages():
    """User messages never show the reasoning button."""
    html = _render_message({"role": "user", "reasoning": "hidden"})
    assert _extract_reasoning_button(html) == ""


def test_reasoning_button_uses_the_link_primitive():
    """The toggle's look comes from the primitive layer, not from utilities."""
    html = _render_message({"reasoning": "hidden", "segments": REASONING_SEGMENTS})
    btn = _extract_reasoning_button(html)
    assert 'class="reasoning-toggle-btn link' in btn, btn
    assert 'data-ui="reasoning-toggle-btn"' in btn, btn


def test_empty_segments_do_not_resurrect_raw_content():
    """A display regex can strip every segment; an empty segment list must not
    fall back to the unfiltered raw content."""
    html = _render_message({"content": "<think>secret</think>", "segments": []})
    assert 'class="message-content' not in html


def test_missing_segments_still_fall_back_to_raw_content():
    """Legacy messages with no computed segments keep the raw-content path."""
    html = _render_message({"content": "legacy text"})
    html = html.replace('data-raw-content="legacy text"', "")
    assert "legacy text" in html


def test_first_reasoning_block_has_no_head():
    """Index-0 reasoning is a headless panel: only its body, hidden until the
    rail's toggle opens it — no strip, no toggle of its own."""
    html = _render_message({"reasoning": "hidden", "segments": REASONING_SEGMENTS})
    block = re.search(
        r'<div class="disclosure reasoning-block pl-stream".*?data-think-id="0"(.*?)</div>\s*\n',
        html,
        re.S,
    ).group(1)
    assert "<summary" not in block, block
    assert "reasoning-toggle-btn" not in block, block
    assert "reasoning-content markdown-content hidden" in block, block


class _Ext:
    def __init__(self, name, description, roles, triggers=None, icon=""):
        self.name = name
        self.description = description
        self.roles = roles
        self.triggers = triggers if triggers is not None else ["manual"]
        self.icon = icon


def _render_with_extensions(enabled_extensions, role="assistant"):
    return env.get_template("chat/message.html").render(
        message={
            "id": "m1", "role": role, "position": 1, "active_index": 0,
            "variant_count": 1, "content": "Hello", "model_name": "m",
            "created_at": "2024-01-01T00:00:00+00:00", "attachments": [],
        },
        character={"name": "Assistant", "image_path": None},
        persona={"name": "User", "avatar_path": None},
        is_latest=True, msg_index=1, chat_id="c1",
        enabled_extensions=enabled_extensions,
    )


def test_extension_button_rendered_for_matching_role():
    html = _render_with_extensions([_Ext("caps_rewrite", "Rewrite it", ["assistant"])])
    assert "data-action=\"actionRunExtension\"" in html
    assert "data-ext-name=\"caps_rewrite\"" in html
    assert "Rewrite it" in html


def test_extension_button_absent_for_nonmatching_role():
    html = _render_with_extensions([_Ext("tts", "Read aloud", ["user"])], role="assistant")
    assert "actionRunExtension" not in html


def test_extension_button_absent_when_none_enabled():
    html = _render_with_extensions([])
    assert "actionRunExtension" not in html


def test_extension_button_absent_for_non_manual_trigger():
    # An extension that only auto-runs (e.g. on generation_end) has no toolbar button.
    html = _render_with_extensions([_Ext("auto_rewrite", "Rewrite", ["assistant"], triggers=["generation_end"])])
    assert "actionRunExtension" not in html


def test_extension_uses_custom_icon():
    icon = "<svg viewBox='0 0 24 24'><path d='M0 0'/></svg>"
    html = _render_with_extensions([_Ext("tts", "Read aloud", ["assistant"], icon=icon)])
    assert icon in html
    # The raw SVG must be wrapped in a sized `.ext-icon` span so an
    # un-specified `viewBox` doesn't blow out the toolbar button.
    assert 'class="ext-icon w-4 h-4 shrink-0"' in html
    assert f'class="ext-icon w-4 h-4 shrink-0">{icon}' in html


MESSAGE_TEMPLATES_FIXTURE = Path("tests/frontend/fixtures/message-templates.html")


def test_message_templates_fixture_is_current():
    """The JS tests clone these templates from a checked-in fixture. If a message
    macro changes, the fixture must be regenerated, otherwise the frontend tests
    keep validating the old markup."""
    rendered = env.get_template("chat/message-templates.html").render().strip()
    assert MESSAGE_TEMPLATES_FIXTURE.exists(), "message templates fixture is missing"
    assert rendered == MESSAGE_TEMPLATES_FIXTURE.read_text().strip(), (
        "fixtures/message-templates.html is stale — regenerate it from "
        "partials/chat/message-templates.html"
    )
