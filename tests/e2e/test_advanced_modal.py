"""The Advanced modal: five tabs, each loading its own collection, and a real
backup written to disk."""

import time
from pathlib import Path

import pytest
from playwright.async_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio(loop_scope="session")]


async def open_advanced(page, app):
    await page.goto(app.url + "/")
    await page.locator(".sidebar-section .nav", has_text="Advanced").click()
    await expect(page.locator("#modal-advanced")).to_be_visible()


async def open_tab(page, label):
    await page.locator("#modal-advanced .tab-bar").get_by_role("button", name=label, exact=True).click()


async def test_every_tab_loads_its_collection(page, app, world):
    await open_advanced(page, app)

    # Tools: the builtin adapters are listed with their enable switches.
    await open_tab(page, "Tools")
    await expect(page.locator("#tools-modal-data")).to_contain_text("read_file")
    await expect(page.locator("#tools-modal-data")).to_contain_text("execute_shell")

    # Extensions: the sample extensions shipped in the repo are discovered.
    await open_tab(page, "Extensions")
    await expect(page.locator("#extensions-modal-data .tool-categories")).to_be_visible()

    # Regex and Structured start empty on a fresh install.
    await open_tab(page, "Regex")
    await expect(page.locator("#regex-scripts-container")).to_contain_text("No")

    await open_tab(page, "Structured")
    await expect(page.locator("#structured-responses-container")).to_contain_text("No")

    # Backups: nothing yet.
    await open_tab(page, "Backups")
    await expect(page.locator("#backups-list")).to_contain_text("No backups yet")

    assert page.js_errors == []


async def test_create_backup_writes_an_archive(page, app, world):
    await open_advanced(page, app)
    await open_tab(page, "Backups")
    await expect(page.locator("#backups-list")).to_contain_text("No backups yet")

    await page.locator("#btn-create-backup").click()

    # The row appears in the list and the archive exists on disk.
    rows = page.locator("#backups-list .backup-row")
    await expect(rows).to_have_count(1)

    backups_dir = Path(app.db_path).parent / "backups"
    deadline = time.time() + 10
    archives = []
    while time.time() < deadline and not archives:
        archives = sorted(backups_dir.glob("*.focus"))
        time.sleep(0.1)
    assert archives, "no archive was written"

    await expect(page.locator('[data-ui="backup-count"]')).to_have_text("1")
    assert page.js_errors == []
