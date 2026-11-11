"""Entity lifecycle: soft delete, the trash bin, restore, hard delete."""

import uuid

import pytest
from playwright.async_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


async def _until(page, predicate, timeout=5000):
    """Poll a server-side fact; the browser has already moved on by then."""
    waited = 0
    while waited < timeout:
        if predicate():
            return True
        await page.wait_for_timeout(100)
        waited += 100
    return False


async def test_character_delete_restore_and_purge(page, app, world, db):
    name = f"Doomed {uuid.uuid4().hex[:6]}"
    created = world.client.post("/api/characters/", json={"name": name})
    assert created.status_code == 201, created.text
    char_id = created.json()["id"]

    await page.goto(app.url + "/")
    await page.locator(".sidebar-section .nav", has_text="Characters").click()
    grid = page.locator("#char-modal-grid")
    row = grid.locator("[data-ui='entity-row']", has_text=name)
    await expect(row).to_be_visible()

    await row.get_by_role("button", name="Delete character").click()
    await page.locator("#global-confirm-btn").click()
    await expect(row).to_have_count(0)

    stored = db.execute("SELECT is_deleted FROM characters WHERE id = ?", (char_id,)).fetchone()
    assert stored["is_deleted"] == 1, "delete did not reach the database"

    # Trash Bin → Restore. The restore dialog defaults to bringing chats back too.
    await page.locator("#characters-modal-body-inner button", has_text="Trash Bin").click()
    await expect(page.locator("#modal-trash")).to_be_visible()
    trash_row = page.locator("#modal-trash-body .row", has_text=name)
    await expect(trash_row).to_be_visible()
    await trash_row.get_by_role("button", name="Restore").click()
    await page.locator("#global-confirm-btn").click()
    await expect(page.locator("#modal-trash")).to_be_hidden()

    restored = db.execute("SELECT is_deleted FROM characters WHERE id = ?", (char_id,)).fetchone()
    assert restored["is_deleted"] == 0, "restore did not reach the database"
    await expect(page.locator("#char-modal-grid [data-ui='entity-row']", has_text=name)).to_have_count(1)

    # Delete again, then purge from the trash for good.
    await page.locator("#char-modal-grid [data-ui='entity-row']", has_text=name).get_by_role(
        "button", name="Delete character"
    ).click()
    await page.locator("#global-confirm-btn").click()
    await page.locator("#characters-modal-body-inner button", has_text="Trash Bin").click()
    await expect(page.locator("#modal-trash-body .row", has_text=name)).to_be_visible()
    await page.locator("#modal-trash-body .row", has_text=name).get_by_role("button", name="Delete forever").click()
    await page.locator("#global-confirm-btn").click()

    purged = await _until(
        page, lambda: db.execute("SELECT id FROM characters WHERE id = ?", (char_id,)).fetchone() is None
    )
    assert purged, "the character survived a hard delete"
    assert page.js_errors == []
