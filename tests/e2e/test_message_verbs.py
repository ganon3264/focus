"""Message verbs: stop, regenerate, swipe, continue, edit, delete, pin.

Setup is HTTP; every assertion is about what a click in a real browser did.
"""

import uuid

import pytest
from playwright.async_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


def _reply() -> str:
    return f"Reply {uuid.uuid4().hex[:6]}"


async def open_chat(page, app, chat):
    await page.goto(f"{app.url}/chat/{chat['id']}")
    await expect(page.locator("#chat-input")).to_be_visible()


async def send(page, text):
    await page.locator("#chat-input").fill(text)
    await page.locator("#send-btn").click()


def assistant_messages(page):
    return page.locator('#message-list .message[data-role="assistant"]')


def variants(db, chat_id):
    return db.execute(
        """
        SELECT m.role, m.active_index, v.variant_index, v.content, v.segments_json
          FROM messages m
          JOIN message_variants v ON v.message_id = m.id
         WHERE m.chat_id = ?
         ORDER BY m.position, v.variant_index
        """,
        (chat_id,),
    ).fetchall()


async def test_stop_mid_stream_keeps_the_partial(page, app, llm, world, db):
    chat = world.new_chat()
    await open_chat(page, app, chat)

    full = "The valley road winds past " * 12
    llm.chunk_delay = 0.05
    llm.reply(full)
    try:
        await send(page, "Tell me a long story")
        await expect(page.locator("#stop-btn")).to_be_visible()
        await page.wait_for_timeout(600)
        await page.locator("#stop-btn").click()
        await expect(page.locator("#send-btn")).to_be_visible()
    finally:
        llm.chunk_delay = 0.0

    await expect(page.locator("#message-list")).to_contain_text("The valley road winds")

    rows = variants(db, chat["id"])
    assistant = [r for r in rows if r["role"] == "assistant"]
    assert len(assistant) == 1
    saved = assistant[0]["content"] or ""
    assert saved.startswith("The valley road winds"), saved
    assert saved != full, "the stream was not actually interrupted"
    assert saved == full[: len(saved)], "the persisted text is not a prefix of the reply"


async def test_regenerate_adds_a_variant_and_swipe_returns_to_the_first(page, app, llm, world, db):
    chat = world.new_chat()
    await open_chat(page, app, chat)

    first, second = _reply(), _reply()
    llm.reply(first)
    await send(page, "Hello")
    await expect(page.locator("#message-list")).to_contain_text(first)

    llm.reply(second)
    msg = assistant_messages(page).last
    await msg.hover()
    await msg.get_by_role("button", name="Regenerate").click()
    await expect(page.locator("#message-list")).to_contain_text(second)
    await expect(msg.locator('[data-ui="swipe-counter"]')).to_have_text("2/2")

    assistant = [r for r in variants(db, chat["id"]) if r["role"] == "assistant"]
    assert [r["content"] for r in assistant] == [first, second]

    await msg.hover()
    await msg.get_by_role("button", name="Previous variant").click()
    await expect(msg.locator('[data-ui="swipe-counter"]')).to_have_text("1/2")
    await expect(page.locator("#message-list")).to_contain_text(first)


async def test_continue_appends_to_the_same_message(page, app, llm, world, db):
    chat = world.new_chat()
    await open_chat(page, app, chat)

    llm.reply("The road begins")
    await send(page, "Hello")
    await expect(page.locator("#message-list")).to_contain_text("The road begins")

    llm.reply(" at the ford.")
    msg = assistant_messages(page).last
    await msg.hover()
    await msg.get_by_role("button", name="Continue").click()
    await expect(page.locator("#message-list")).to_contain_text("at the ford.")

    assistant = [r for r in variants(db, chat["id"]) if r["role"] == "assistant"]
    assert len(assistant) == 1, "continue must extend the turn, not fork a variant"
    assert assistant[0]["content"] == "The road begins at the ford."
    assert "The road begins" in llm.last_request_messages()[-1]["content"], (
        "the prefill was not sent as the assistant turn"
    )


async def test_edit_message_rewrites_the_stored_turn(page, app, llm, world, db):
    chat = world.new_chat()
    await open_chat(page, app, chat)

    llm.reply(_reply())
    await send(page, "Hello")
    await expect(assistant_messages(page)).to_have_count(1)

    msg = assistant_messages(page).last
    await msg.hover()
    await msg.get_by_role("button", name="Edit message").click()
    editor = page.locator("#modal-edit-message")
    await expect(editor).to_be_visible()
    field = editor.locator("textarea").first
    await field.fill("An edited turn.")
    await editor.locator("button[type='submit']").click()
    await expect(editor).to_be_hidden()

    await expect(page.locator("#message-list")).to_contain_text("An edited turn.")
    # An edit is a revision, not a rewrite: the old text stays swipeable.
    await expect(msg.locator('[data-ui="swipe-counter"]')).to_have_text("2/2")
    assistant = [r for r in variants(db, chat["id"]) if r["role"] == "assistant"]
    assert len(assistant) == 2
    assert assistant[1]["content"] == "An edited turn."
    assert assistant[0]["content"] != "An edited turn."


async def test_delete_mode_removes_the_turn(page, app, llm, world, db):
    chat = world.new_chat()
    await open_chat(page, app, chat)

    llm.reply(_reply())
    await send(page, "Hello")
    await expect(assistant_messages(page)).to_have_count(1)

    msg = assistant_messages(page).last
    await msg.hover()
    await msg.get_by_role("button", name="Delete messages").click()

    # The trash key starts a range selection at the clicked turn, so it is
    # already ticked — clicking the box would deselect it.
    await expect(msg.locator('[data-ui="msg-select-checkbox"]')).to_be_checked()
    await page.locator("#delete-selected-btn").click()
    await page.locator("#global-confirm-btn").click()

    await expect(page.locator("#message-list .message")).to_have_count(1)
    rows = variants(db, chat["id"])
    assert [r["role"] for r in rows] == ["user"]


async def test_pin_survives_a_reload(page, app, llm, world, db):
    chat = world.new_chat()
    await open_chat(page, app, chat)

    llm.reply(_reply())
    await send(page, "Hello")
    await expect(assistant_messages(page)).to_have_count(1)

    msg = assistant_messages(page).last
    await msg.hover()
    await msg.get_by_role("button", name="Toggle pin").click()
    await expect(msg.get_by_role("button", name="Toggle pin")).to_have_attribute("data-pinned", "1")

    pinned = db.execute("SELECT pinned FROM messages WHERE chat_id = ? AND role = 'assistant'", (chat["id"],)).fetchone()
    assert pinned["pinned"] == 1, "the pin never reached the database"

    await page.reload()
    await expect(assistant_messages(page).last.get_by_role("button", name="Toggle pin")).to_have_attribute(
        "data-pinned", "1"
    )
