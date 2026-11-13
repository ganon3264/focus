"""A long chat refreshes only the messages that changed.

The post-stream refresh asks the server for the stale nodes alone; the response
still carries the whole position order, so the list must come out exactly as a
full render would leave it.
"""

import re
import sqlite3
import uuid
from datetime import UTC, datetime

import pytest
from playwright.async_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]

SEEDED = 30


def _seed(app, chat_id: str) -> None:
    now = datetime.now(UTC).isoformat()
    with sqlite3.connect(app.db_path, timeout=5) as conn:
        start = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM messages WHERE chat_id = ?", (chat_id,)
        ).fetchone()[0]
        for i in range(SEEDED):
            msg_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO messages (id, chat_id, role, position, active_index, created_at)"
                " VALUES (?, ?, ?, ?, 0, ?)",
                (msg_id, chat_id, "user" if i % 2 == 0 else "assistant", start + i, now),
            )
            conn.execute(
                "INSERT INTO message_variants"
                " (id, message_id, variant_index, content, created_at, model_name)"
                " VALUES (?, ?, 0, ?, ?, 'fake-model')",
                (str(uuid.uuid4()), msg_id, f"Seeded turn {i}", now),
            )
        conn.commit()


def _rendered_nodes(html: str) -> int:
    return len(re.findall(r'<div class="message frame[^"]*" data-ui="message"', html))


async def test_post_stream_refresh_asks_for_the_changed_messages_only(page, app, llm, world):
    chat = world.new_chat("Long chat")
    _seed(app, chat["id"])

    await page.goto(f"{app.url}/chat/{chat['id']}")
    await expect(page.locator('#message-list [data-ui="message"]').last).to_be_visible()

    # The last live node must survive the refresh: a narrowed render replaces
    # only the stale nodes, a full one replaces all of them. It is re-rendered
    # for its own reason (it stops being the latest turn), so stand in for it
    # with the one above.
    tail_ids = await page.evaluate(
        """() => {
             const all = document.querySelectorAll('#message-list [data-ui="message"]');
             const previous = all[all.length - 1];
             const above = all[all.length - 2];
             above.dataset.untouched = '1';
             return { previous: previous.dataset.messageId, above: above.dataset.messageId };
           }"""
    )

    responses = []

    def on_response(resp):
        if "/partials/message-list/" in resp.url:
            responses.append(resp)

    page.on("response", on_response)

    reply = f"Answer {uuid.uuid4().hex[:6]}"
    llm.reply(reply)
    await page.locator("#chat-input").fill("One more turn")
    await page.locator("#send-btn").click()
    await expect(page.locator("#message-list")).to_contain_text(reply)

    assert responses, "the post-stream message refresh never ran"
    for resp in responses:
        html = await resp.text()
        assert "ids=" in resp.url, f"the whole list was fetched: {resp.url}"
        order = re.search(r'data-order="([^"]*)"', html).group(1).split(",")
        assert len(order) == SEEDED + 2, "the response still carries the whole order"

        rendered = set(re.findall(r'data-message-id="([^"]+)"', html))
        assert rendered == {order[-2], order[-1], tail_ids["previous"]}, (
            f"the refresh rendered {set(rendered) - {order[-2], order[-1], tail_ids['previous']}}"
        )
        assert tail_ids["above"] not in rendered

    assert await page.evaluate(
        "() => !!document.querySelector('#message-list [data-ui=\"message\"][data-untouched=\"1\"]')"
    ), "an untouched message was re-rendered"

    # Every live node's index still matches its place in the server's order.
    mismatched = await page.evaluate(
        """() => {
             const order = document.getElementById('message-list-data').dataset.order.split(',');
             const bad = [];
             document.querySelectorAll('#message-list [data-ui="message"]').forEach((el) => {
               const expected = String(order.indexOf(el.dataset.messageId) + 1);
               if (expected !== el.dataset.msgIndex) bad.push([el.dataset.messageId, expected, el.dataset.msgIndex]);
             });
             return bad;
           }"""
    )
    assert mismatched == []

    total = SEEDED + 2
    assert await page.evaluate(
        "() => document.querySelectorAll('#message-list [data-ui=\"message\"],"
        " #message-list [data-ui=\"message-placeholder\"]').length"
    ) == total

    # Regenerate belongs to the newest assistant turn only.
    assert await page.evaluate(
        '() => document.querySelectorAll("#message-list [data-action=\\"actionTriggerRegeneration\\"]").length'
    ) == 1

    assert page.js_errors == []

    await page.reload()
    assert await page.evaluate(
        "() => document.querySelectorAll('#message-list [data-ui=\"message\"],"
        " #message-list [data-ui=\"message-placeholder\"]').length"
    ) == total
