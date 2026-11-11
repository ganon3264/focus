"""The core flows, driven the way a user drives them.

Each test asserts on what the browser shows *and* on what landed in SQLite,
because either one alone can be right while the other is wrong.
"""

import json
import uuid

import pytest
from playwright.async_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


def _unique(prefix: str) -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


async def open_characters(page, app):
    await page.goto(app.url + "/")
    await page.locator(".sidebar-section .nav", has_text="Characters").click()
    await expect(page.locator("#characters-modal-body-inner .modal-band-head")).to_be_visible()


async def create_character(page, app, name):
    await open_characters(page, app)
    await page.locator("#characters-modal-body-inner .modal-band-head button", has_text="New").click()
    await page.locator("#new-char-name-input").fill(name)
    await page.locator("#global-confirm-btn").click()
    await expect(page.locator("#char-modal-grid [data-ui='entity-row']", has_text=name)).to_be_visible()
    return name


async def create_persona(page, app, name):
    await page.goto(app.url + "/")
    await page.locator(".sidebar-section .nav", has_text="Personas").click()
    await expect(page.locator("#personas-modal-body-inner .modal-band-head")).to_be_visible()
    await page.locator("#personas-modal-body-inner .modal-band-head button", has_text="New").click()
    await page.locator("#new-persona-name-input").fill(name)
    await page.locator("#global-confirm-btn").click()
    await expect(page.locator("#persona-modal-grid [data-ui='entity-row']", has_text=name)).to_be_visible()
    return name


async def create_preset(page, app, name):
    await page.goto(app.url + "/")
    await page.locator("#preset-selector-wrapper").click()
    await expect(page.locator("#presets-modal-body-inner .modal-band-head")).to_be_visible()
    await page.locator("#presets-modal-body-inner button", has_text="New").click()
    await page.locator("#preset-name-input").fill(name)
    await page.locator("#preset-name-submit").click()
    await expect(page.locator("#preset-current-name")).to_have_text(name)
    await close_modal(page, "modal-presets")
    return name


async def describe_character(page, app, name, description):
    """Open the editor from the card and save a description."""
    await open_characters(page, app)
    row = page.locator("#char-modal-grid [data-ui='entity-row']", has_text=name)
    await row.get_by_role("button", name="Edit character").click()
    await expect(page.locator("#edit-char-name")).to_have_value(name)
    await page.locator("#edit-char-desc").fill(description)
    await page.locator("#edit-char-form button[type='submit']").click()
    await expect(page.locator("#modal-edit-character")).to_be_hidden()
    await close_modal(page, "modal-characters")


async def create_provider(page, app, llm, name):
    await page.goto(app.url + "/")
    await page.locator(".sidebar-section .nav", has_text="Providers").click()
    await expect(page.locator("#providers-modal-body-inner")).not_to_have_text("Loading…")
    await page.get_by_role("button", name="Add Provider").click()

    await page.locator("#prov-form-name").fill(name)
    await page.locator("#prov-form-base-url").fill(llm.base_url)
    await page.locator("#model-text-prov-form").fill("fake-model")
    await page.locator("#prov-form-submit-btn").click()

    row = page.locator("#providers-grid .provider-row", has_text=name)
    await expect(row).to_be_visible()
    return row


async def close_modal(page, modal_id):
    await page.locator(f"#{modal_id} .modal-head button[data-modal-id='{modal_id}']").click()
    await expect(page.locator(f"#{modal_id}")).to_be_hidden()


async def start_chat_with(page, app, character_name, provider_name):
    """Select the provider, then pick the character — the order a user does it."""
    await page.goto(app.url + "/")
    await page.locator(".sidebar-section .nav", has_text="Providers").click()
    await expect(page.locator("#providers-grid")).to_be_visible()
    await page.locator("#providers-grid .provider-row", has_text=provider_name).click()
    await close_modal(page, "modal-providers")

    await page.locator(".sidebar-section .nav", has_text="Characters").click()
    await expect(page.locator("#characters-modal-body-inner .modal-band-head")).to_be_visible()
    await page.locator("#char-modal-grid [data-ui='entity-row']", has_text=character_name).click()

    await page.get_by_role("button", name="Start Chat").click()
    await expect(page.locator("#chat-input")).to_be_visible()


async def test_home_loads(page, app):
    await page.goto(app.url + "/")
    await expect(page.get_by_text("Welcome to Focus")).to_be_visible()
    assert page.js_errors == []


async def test_add_character(page, app, db):
    name = _unique("Aria")
    await create_character(page, app, name)

    assert page.js_errors == []
    row = db.execute("SELECT id FROM characters WHERE name = ? AND is_deleted = 0", (name,)).fetchone()
    assert row, "the character never reached the database"


async def test_add_persona(page, app, db):
    name = _unique("Wanderer")
    await create_persona(page, app, name)

    assert page.js_errors == []
    assert db.execute("SELECT id FROM personas WHERE name = ? AND is_deleted = 0", (name,)).fetchone()


async def test_add_provider_points_at_the_upstream(page, app, llm, db):
    name = _unique("Fake")
    row = await create_provider(page, app, llm, name)

    stored = db.execute("SELECT type, base_url, model FROM providers WHERE name = ?", (name,)).fetchone()
    assert stored, "the provider never reached the database"
    assert stored["type"] == "openai_compat"
    assert stored["base_url"] == llm.base_url
    assert stored["model"] == "fake-model"

    await row.click()
    await close_modal(page, "modal-providers")
    await expect(page.locator("#status-provider")).to_have_text(name)
    await expect(page.locator("#status-provider")).to_have_attribute("title", f"{name} · openai_compat")
    await expect(page.locator("#status-model")).to_have_text("fake-model")
    assert page.js_errors == []


async def test_chat_round_trip(page, app, llm, db):
    character = _unique("Aria")
    provider = _unique("Fake")
    preset = _unique("Preset")
    description = "A cartographer who has never left the valley."
    reply = f"Traveller, the road is long {uuid.uuid4().hex[:6]}."
    llm.reply(reply)

    await create_character(page, app, character)
    await describe_character(page, app, character, description)
    await create_preset(page, app, preset)
    await create_provider(page, app, llm, provider)
    await close_modal(page, "modal-providers")

    await start_chat_with(page, app, character, provider)
    await expect(page.locator("#status-provider")).to_have_text(provider)

    await page.locator("#chat-input").fill("Hello there")
    await page.locator("#send-btn").click()

    await expect(page.locator("#message-list")).to_contain_text(reply)

    chat_id = page.url.rsplit("/", 1)[-1]
    rows = db.execute(
        """
        SELECT m.role, v.content, v.segments_json
          FROM messages m
          JOIN message_variants v ON v.message_id = m.id AND v.variant_index = m.active_index
         WHERE m.chat_id = ?
         ORDER BY m.position
        """,
        (chat_id,),
    ).fetchall()
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "Hello there"
    assert reply in (rows[1]["segments_json"] or "")

    prompt = json.dumps(llm.last_request_messages())
    assert "Hello there" in prompt
    assert description in prompt, "the character card never made it into the prompt"

    block = db.execute(
        """
        SELECT b.content
          FROM preset_blocks b
          JOIN chats c ON c.preset_id = b.preset_id
         WHERE c.id = ? AND b.block_type = 'text' AND b.enabled = 1
         ORDER BY b.position LIMIT 1
        """,
        (chat_id,),
    ).fetchone()
    assert block and block["content"] in prompt, "the preset's blocks never made it into the prompt"

    await page.reload()
    await expect(page.locator("#message-list")).to_contain_text(reply)
    await expect(page.locator("#message-list")).to_contain_text("Hello there")
    assert page.js_errors == []
