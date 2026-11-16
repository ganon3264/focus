"""First launch: the setup checklist has to tell the truth as it is walked.

Every step is driven through the checklist's own verb, and asserted on the
checklist itself — a row that stays stale while the entity behind it exists is
exactly the failure this file exists to catch. The optional act (persona) is a
muted line under the greeter's CTA, not a row: the checklist lists only what
blocks you, and its last step replaces the pane.
"""

import pytest
import pytest_asyncio
from playwright.async_api import expect

from tests.e2e.conftest import spawn_app

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


@pytest_asyncio.fixture(scope="module", loop_scope="session")
async def fresh_app(tmp_path_factory):
    with spawn_app(tmp_path_factory.mktemp("e2e-first-launch")) as instance:
        yield instance


def step(page, slug):
    return page.locator(f"#setup-checklist [data-setup-step='{slug}']")


def persona_link(page):
    return page.locator("#setup-checklist").get_by_role("button", name="describe yourself")


async def test_setup_checklist_tracks_what_the_user_just_did(page, fresh_app):
    await page.goto(fresh_app.url + "/")

    checklist = page.locator("#setup-checklist")
    await expect(checklist).to_contain_text("0/3")
    await expect(step(page, "provider")).to_contain_text("Connect an API provider")
    await expect(step(page, "character")).to_contain_text("Create or import")
    await expect(checklist.locator("[data-setup-step]")).to_have_count(3)
    await expect(persona_link(page)).to_have_count(0)
    await expect(page.locator('#right-chat-action button[data-ui="chat-action"]')).to_have_attribute("title", "Add Character")

    # A created character reaches the checklist and the right pane without a
    # reload, and the row offers a way to pick it.
    await step(page, "character").get_by_role("button", name="Add").click()
    await page.locator("#characters-modal-body-inner .modal-band-head button", has_text="New").click()
    await page.locator("#new-char-name-input").fill("First Character")
    await page.locator("#global-confirm-btn").click()
    await expect(step(page, "character")).to_contain_text("Choose a character")
    await expect(page.locator('#right-chat-action button[data-ui="chat-action"]')).to_have_attribute("title", "New Chat")
    await expect(checklist).to_contain_text("1/3")
    await page.keyboard.press("Escape")

    await step(page, "character").get_by_role("button", name="Select").click()
    await page.locator("#char-modal-grid [data-ui='entity-row']", has_text="First Character").click()
    await page.wait_for_url("**character_id=*")
    await expect(step(page, "character")).to_contain_text("First Character")
    await expect(step(page, "character")).to_contain_text("Done")

    # Adding the first provider selects it: the first one you add is the one you
    # mean, and a created-but-unselected provider strands the user a modal deep.
    await step(page, "provider").get_by_role("button", name="Add").click()
    await page.locator('[data-action="actionOpenProviderCreateModal"]').click()
    await page.locator("#prov-form-name").fill("First Provider")
    await page.locator("#prov-form-base-url").fill("http://127.0.0.1:1/v1")
    await page.locator("#model-text-prov-form").fill("fake-model")
    await page.locator("#prov-form-submit-btn").click()
    await expect(step(page, "provider")).to_contain_text("Done")
    await expect(page.locator("#status-provider")).to_have_text("First Provider")
    await expect(checklist).to_contain_text("2/3")
    await page.keyboard.press("Escape")

    # The last step hands the pane over to the greeter.
    await step(page, "preset").get_by_role("button", name="Create").click()
    await page.locator("#preset-name-input").fill("First Preset")
    await page.locator("#preset-name-submit").click()
    await expect(checklist).to_contain_text("First Character")
    await expect(checklist.locator("[data-setup-step]")).to_have_count(0)
    await expect(checklist.get_by_role("button", name="Start Chat")).to_be_visible()

    # The optional act survives the pane switch instead of vanishing mid-list,
    # and retires itself once done.
    await expect(persona_link(page)).to_be_visible()
    await persona_link(page).click()
    await expect(page.locator("#edit-persona-name")).to_have_value("User")
    await page.locator("#edit-persona-desc").fill("A traveller with a full water skin.")
    await page.locator("#edit-persona-form button[type='submit']").click()
    await expect(page.locator("#modal-edit-persona")).to_be_hidden()
    await expect(persona_link(page)).to_have_count(0)
    assert page.js_errors == []
