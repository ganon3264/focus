"""Alternate greetings: the variant rail in the character editor.

The rail is a server-rendered partial that swaps itself on every verb, so the
test drives prev/next/add/delete and then checks what the card actually holds.
"""

import json
import uuid

import pytest
from playwright.async_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


def _card(db, char_id):
    row = db.execute("SELECT card_json FROM characters WHERE id = ?", (char_id,)).fetchone()
    card = json.loads(row["card_json"])
    return card.get("data", card)


async def open_editor(page, app, name):
    await page.goto(app.url + "/")
    await page.locator(".sidebar-section .nav", has_text="Characters").click()
    row = page.locator("#char-modal-grid [data-ui='entity-row']", has_text=name)
    await expect(row).to_be_visible()
    await row.get_by_role("button", name="Edit character").click()
    await expect(page.locator("#modal-edit-character")).to_be_visible()


async def save(page):
    await page.locator("#edit-char-form button[type='submit']").click()
    await expect(page.locator("#modal-edit-character")).to_be_hidden()


async def test_greeting_variants_round_trip(page, app, world, db):
    name = f"Greeter {uuid.uuid4().hex[:6]}"
    created = world.client.post(
        "/api/characters/",
        json={
            "name": name,
            "first_mes": "First greeting",
            "alternate_greetings": ["Second greeting", "Third greeting"],
        },
    )
    assert created.status_code == 201, created.text
    char_id = created.json()["id"]

    await open_editor(page, app, name)

    count = page.locator("#edit-char-greeting-count")
    text = page.locator("#edit-char-greeting")

    assert await text.input_value() == "First greeting"
    await expect(count).to_have_text("1/3")
    await expect(page.locator("#edit-char-greeting-prev")).to_be_disabled()

    # Next: the rail swaps itself, keeping the typed text of the variant left behind.
    await page.locator("#edit-char-greeting-next").click()
    await expect(count).to_have_text("2/3")
    assert await text.input_value() == "Second greeting"

    # ...and back, which is the only thing that exercises the merge of an
    # edited variant into the list before stepping away from it.
    await page.locator("#edit-char-greeting-next").click()
    await expect(count).to_have_text("3/3")
    assert await text.input_value() == "Third greeting"
    await page.locator("#edit-char-greeting-prev").click()
    await expect(count).to_have_text("2/3")
    assert await text.input_value() == "Second greeting"

    await text.fill("Second, revised")
    await save(page)

    card = _card(db, char_id)
    assert card["first_mes"] == "First greeting"
    assert card["alternate_greetings"] == ["Second, revised", "Third greeting"]

    # Add a fourth variant, then remove it again.
    await open_editor(page, app, name)
    await page.get_by_role("button", name="Add greeting variant").click()
    await expect(count).to_have_text("4/4")
    assert await text.input_value() == ""

    await text.fill("Fourth variant")
    await save(page)
    assert _card(db, char_id)["alternate_greetings"][-1] == "Fourth variant"

    # Delete goes through the app's confirm modal (htmx:confirm is intercepted).
    await open_editor(page, app, name)
    for position in (2, 3, 4):
        await page.locator("#edit-char-greeting-next").click()
        await expect(count).to_have_text(f"{position}/4")
    await page.get_by_role("button", name="Delete greeting").click()

    await expect(page.locator("#global-confirm-modal")).to_be_visible()
    await page.locator("#global-confirm-btn").click()
    await expect(count).to_have_text("3/3")

    await save(page)
    card = _card(db, char_id)
    assert card["first_mes"] == "First greeting"
    assert card["alternate_greetings"] == ["Second, revised", "Third greeting"]
    assert page.js_errors == []
