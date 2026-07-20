"""Tests for the chat/message.html template reasoning button.

Verifies that the server-rendered "Reasoning" button has the
`reasoning-toggle-btn` class so the client-side `syncReasoningButtons`
helper can manage its visibility (it must be hidden while a new stream
is in progress and shown only once `details.reasoning` is in the
content).
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


def test_reasoning_button_present_when_content_has_think_tags():
    """Server should render the button when content contains <think>."""
    html = _render_message({"content": "<think>hidden</think>answer"})
    btn = _extract_reasoning_button(html)
    assert btn, "Expected reasoning button to be rendered"
    assert "reasoning-toggle-btn" in btn, (
        f"Reasoning button must have 'reasoning-toggle-btn' class so "
        f"syncReasoningButtons() can manage it. Got: {btn}"
    )


def test_reasoning_button_absent_when_no_think_tags():
    """No button when content has no <think> tags."""
    html = _render_message({"content": "plain text response"})
    assert _extract_reasoning_button(html) == ""


def test_reasoning_button_absent_for_position_zero():
    """Greeting message (position 0) never shows the reasoning button."""
    html = _render_message({"position": 0, "content": "<think>hidden</think>hello"})
    assert _extract_reasoning_button(html) == ""


def test_reasoning_button_absent_for_user_messages():
    """User messages never show the reasoning button."""
    html = _render_message({"role": "user", "content": "<think>hidden</think>user"})
    assert _extract_reasoning_button(html) == ""


def test_reasoning_button_class_unchanged():
    """Regression: existing class list is preserved alongside the new one."""
    html = _render_message({"content": "<think>hidden</think>answer"})
    btn = _extract_reasoning_button(html)
    for required in (
        "inline-flex",
        "items-center",
        "gap-1",
        "text-muted",
        "transition-colors",
        "cursor-pointer",
    ):
        assert required in btn, f"Missing existing class '{required}' in: {btn}"
