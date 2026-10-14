from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from io import BytesIO
from zipfile import ZipFile

import aiosqlite

from tests.helpers import create_character, create_preset


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _insert_message(db_path: str, chat_id: str, role: str, position: int, content: str) -> str:
    msg_id = str(uuid.uuid4())
    now = _now_iso()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, chat_id, role, position, 0, now),
        )
        await db.execute(
            "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), msg_id, 0, content, now),
        )
        await db.commit()
    return msg_id


def _new_script(**overrides) -> dict:
    body = {
        "scope": "global",
        "name": "Strip slop",
        "pattern": r"A beat\.\s*",
        "replacement": "",
        "placement": "ai",
        "apply_prompt": True,
        "apply_display": True,
        "as_block": False,
    }
    body.update(overrides)
    return body


async def _read_db(tmp_test_dir, sql: str, params: tuple = ()):
    db_path = os.path.join(tmp_test_dir, "test.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        return await cur.fetchall()


class TestCrud:
    async def test_create_and_list_global(self, client):
        resp = await client.post("/api/regex-scripts", json=_new_script())
        assert resp.status_code == 201
        script = resp.json()
        assert script["scope"] == "global"
        assert script["scope_id"] is None
        assert script["enabled"] is True

        listing = (await client.get("/api/regex-scripts")).json()
        assert [s["id"] for s in listing["scripts"]] == [script["id"]]

    async def test_preset_script_requires_scope_id(self, client):
        resp = await client.post("/api/regex-scripts", json=_new_script(scope="preset"))
        assert resp.status_code == 400

    async def test_list_with_preset_includes_global_first(self, client):
        preset = await create_preset(client)
        global_script = (await client.post("/api/regex-scripts", json=_new_script(name="G"))).json()
        preset_script = (
            await client.post(
                "/api/regex-scripts",
                json=_new_script(scope="preset", scope_id=preset["id"], name="P"),
            )
        ).json()

        listing = (await client.get(f"/api/regex-scripts?preset_id={preset['id']}")).json()
        assert [s["id"] for s in listing["scripts"]] == [global_script["id"], preset_script["id"]]

    async def test_update_fields(self, client):
        script = (await client.post("/api/regex-scripts", json=_new_script())).json()
        resp = await client.patch(
            f"/api/regex-scripts/{script['id']}",
            json={"name": "Renamed", "placement": "ai,reasoning", "max_depth": 3, "enabled": False},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["name"] == "Renamed"
        assert updated["placement"] == "ai,reasoning"
        assert updated["max_depth"] == 3
        assert updated["enabled"] is False

    async def test_block_forces_display(self, client):
        # Setting a block forces display on.
        created = (
            await client.post(
                "/api/regex-scripts", json=_new_script(as_block=True, apply_display=False)
            )
        ).json()
        assert created["as_block"] is True
        assert created["apply_display"] is True

        # Display can't be turned off while a block is set.
        script = (
            await client.post("/api/regex-scripts", json=_new_script(as_block=True))
        ).json()
        updated = (
            await client.patch(
                f"/api/regex-scripts/{script['id']}", json={"apply_display": False}
            )
        ).json()
        assert updated["as_block"] is True
        assert updated["apply_display"] is True

        # With the block off, display can be turned off.
        off = (
            await client.patch(
                f"/api/regex-scripts/{script['id']}",
                json={"as_block": False, "apply_display": False},
            )
        ).json()
        assert off["as_block"] is False
        assert off["apply_display"] is False

    async def test_create_draft_with_empty_pattern(self, client):
        # The UI creates a blank row, then the user types the pattern; a draft
        # must be persistable so it can be edited.
        resp = await client.post("/api/regex-scripts", json=_new_script(pattern=""))
        assert resp.status_code == 201
        assert resp.json()["pattern"] == ""

    async def test_update_missing(self, client):
        resp = await client.patch("/api/regex-scripts/nope", json={"name": "x"})
        assert resp.status_code == 404

    async def test_delete(self, client):
        script = (await client.post("/api/regex-scripts", json=_new_script())).json()
        assert (await client.delete(f"/api/regex-scripts/{script['id']}")).status_code == 204
        assert (await client.get("/api/regex-scripts")).json()["scripts"] == []

    async def test_delete_missing(self, client):
        assert (await client.delete("/api/regex-scripts/nope")).status_code == 404

    async def test_invalid_pattern_rejected(self, client):
        resp = await client.post("/api/regex-scripts", json=_new_script(pattern="("))
        assert resp.status_code == 400

    async def test_invalid_placement_rejected(self, client):
        resp = await client.post("/api/regex-scripts", json=_new_script(placement="banana"))
        assert resp.status_code == 400

    async def test_invalid_replacement_rejected(self, client):
        resp = await client.post(
            "/api/regex-scripts", json=_new_script(pattern="(a)", replacement=r"\2")
        )
        assert resp.status_code == 400

    async def test_update_validates_against_existing_pattern(self, client):
        script = (
            await client.post("/api/regex-scripts", json=_new_script(pattern="(a)", replacement="b"))
        ).json()
        resp = await client.patch(f"/api/regex-scripts/{script['id']}", json={"replacement": r"\2"})
        assert resp.status_code == 400

    async def test_reorder(self, client):
        first = (await client.post("/api/regex-scripts", json=_new_script(name="1"))).json()
        second = (await client.post("/api/regex-scripts", json=_new_script(name="2"))).json()
        resp = await client.post(
            "/api/regex-scripts/reorder", json={"ids": [second["id"], first["id"]]}
        )
        assert resp.status_code == 200
        listing = (await client.get("/api/regex-scripts")).json()["scripts"]
        assert [s["id"] for s in listing] == [second["id"], first["id"]]


class TestPreview:
    async def test_preview_applies(self, client):
        resp = await client.post(
            "/api/regex-scripts/preview",
            json={"pattern": r"A beat\.\s*", "replacement": "", "flags": "", "sample": "A beat. Hello."},
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "Hello."

    async def test_preview_flags(self, client):
        resp = await client.post(
            "/api/regex-scripts/preview",
            json={"pattern": "hello", "replacement": "hi", "flags": "i", "sample": "HELLO"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "hi"

    async def test_preview_invalid_pattern(self, client):
        resp = await client.post(
            "/api/regex-scripts/preview",
            json={"pattern": "(", "replacement": "", "flags": "", "sample": "x"},
        )
        assert resp.status_code == 400


class TestPartial:
    async def test_renders_groups(self, client):
        preset = await create_preset(client, "My Preset")
        await client.post("/api/regex-scripts", json=_new_script(name="Global One"))
        await client.post(
            "/api/regex-scripts",
            json=_new_script(scope="preset", scope_id=preset["id"], name="Preset One"),
        )
        resp = await client.get(f"/partials/regex-scripts?preset_id={preset['id']}")
        assert resp.status_code == 200
        assert "Global One" in resp.text
        assert "Preset One" in resp.text
        assert "My Preset" in resp.text
        assert "No global scripts." not in resp.text

    async def test_item_partial_renders_state(self, client):
        script = (await client.post("/api/regex-scripts", json=_new_script())).json()
        await client.patch(f"/api/regex-scripts/{script['id']}", json={"enabled": False})

        resp = await client.get(f"/partials/regex-scripts/item/{script['id']}")
        assert resp.status_code == 200
        assert "arranger-item regex-item disabled" in resp.text
        assert 'style="display: none"' in resp.text

        opened = await client.get(f"/partials/regex-scripts/item/{script['id']}?open=1")
        assert opened.status_code == 200
        assert "expanded" in opened.text
        assert 'style="display: block"' in opened.text

        assert (
            await client.get("/partials/regex-scripts/item/missing")
        ).status_code == 404

    async def test_no_preset_hides_preset_group(self, client):
        resp = await client.get("/partials/regex-scripts")
        assert resp.status_code == 200
        assert "No global scripts." in resp.text
        assert "Select a preset" in resp.text


class TestDisplayIntegration:
    async def test_cosmetic_script_changes_render_not_storage(self, client, tmp_test_dir):
        from tests.helpers import create_chat

        chat = await create_chat(client, title="Regex Chat")
        await _insert_message(
            os.path.join(tmp_test_dir, "test.db"), chat["id"], "assistant", 0, "A beat. Hello"
        )

        before = await client.get(f"/partials/message-list/{chat['id']}")
        assert ">A beat. Hello</div>" in before.text

        await client.post(
            "/api/regex-scripts",
            json=_new_script(
                pattern=r"A beat\.\s*", replacement="", apply_prompt=False, placement="ai"
            ),
        )

        after = await client.get(f"/partials/message-list/{chat['id']}")
        # The rendered content changes; the raw text stays in data-raw-content
        # for the edit modal.
        assert ">A beat. Hello</div>" not in after.text
        assert ">Hello</div>" in after.text
        assert 'data-raw-content="A beat. Hello"' in after.text

        # Storage is untouched.
        rows = await _read_db(tmp_test_dir, "SELECT content FROM message_variants")
        assert rows[0]["content"] == "A beat. Hello"

    async def test_depth_window_limits_display_scope(self, client, tmp_test_dir):
        from tests.helpers import create_chat

        chat = await create_chat(client, title="Depth Chat")
        db_path = os.path.join(tmp_test_dir, "test.db")
        await _insert_message(db_path, chat["id"], "assistant", 0, "A beat. old")
        await _insert_message(db_path, chat["id"], "user", 1, "hi")
        await _insert_message(db_path, chat["id"], "assistant", 2, "A beat. new")

        await client.post(
            "/api/regex-scripts",
            json=_new_script(pattern=r"A beat\.\s*", replacement="", apply_prompt=False, max_depth=0),
        )
        html = (await client.get(f"/partials/message-list/{chat['id']}")).text
        assert ">A beat. old</div>" in html
        assert ">A beat. new</div>" not in html
        assert ">new</div>" in html

    async def test_block_script_renders_collapsible_block(self, client, tmp_test_dir):
        from tests.helpers import create_chat

        chat = await create_chat(client, title="Block Chat")
        await _insert_message(
            os.path.join(tmp_test_dir, "test.db"),
            chat["id"],
            "assistant",
            0,
            "before\n<think>\nsecret\n</think>\nafter",
        )
        await client.post(
            "/api/regex-scripts",
            json=_new_script(
                name="Think",
                pattern=r"<think>(.*?)</think>",
                flags="s",
                replacement="",
                as_block=True,
                placement="ai",
            ),
        )
        html = (await client.get(f"/partials/message-list/{chat['id']}")).text
        assert "<summary>" in html
        assert "Think" in html
        assert "secret" in html
        assert "after" in html
        # Raw content is retained (escaped) for the edit modal.
        assert "&lt;think&gt;" in html


class TestExportRoundtrip:
    async def test_export_carries_global_and_scoped_scripts(self, client):
        preset = await create_preset(client)
        global_script = (await client.post("/api/regex-scripts", json=_new_script(name="G"))).json()
        await client.post(
            "/api/regex-scripts",
            json=_new_script(scope="preset", scope_id=preset["id"], name="P"),
        )

        resp = await client.post("/api/export", json={"presets": [preset["id"]]})
        assert resp.status_code == 200
        with ZipFile(BytesIO(resp.content)) as zf:
            db = json.loads(zf.read("database.json"))

        scripts = {s["name"]: s for s in db["regex_scripts"]}
        assert set(scripts) == {"G", "P"}
        assert scripts["G"]["scope_id"] is None
        # Export re-ids presets; the scoped script must point at the new id.
        assert scripts["P"]["scope_id"] == db["presets"][0]["id"]
        assert scripts["P"]["scope_id"] != preset["id"]
        # Global script ids travel too, but stay distinct from their old value.
        assert scripts["G"]["id"] != global_script["id"]

    async def test_export_omits_scripts_for_unexported_presets(self, client):
        preset = await create_preset(client)
        char = await create_character(client, "Only Char")
        await client.post("/api/regex-scripts", json=_new_script(name="G"))
        await client.post(
            "/api/regex-scripts",
            json=_new_script(scope="preset", scope_id=preset["id"], name="P"),
        )

        resp = await client.post("/api/export", json={"characters": [char["id"]]})
        with ZipFile(BytesIO(resp.content)) as zf:
            db = json.loads(zf.read("database.json"))
        assert [s["name"] for s in db["regex_scripts"]] == ["G"]

    async def test_import_restores_scripts(self, client, tmp_test_dir):
        preset = await create_preset(client)
        await client.post("/api/regex-scripts", json=_new_script(name="G"))
        await client.post(
            "/api/regex-scripts",
            json=_new_script(scope="preset", scope_id=preset["id"], name="P"),
        )

        exported = (await client.post("/api/export", json={"presets": [preset["id"]]})).content
        files = {"file": ("x.focus", BytesIO(exported), "application/zip")}
        imp = await client.post("/api/import", files=files)
        assert imp.status_code == 201

        rows = await _read_db(tmp_test_dir, "SELECT name, scope, scope_id FROM regex_scripts")
        names = {r["name"] for r in rows}
        assert {"G", "P"} <= names
        # 2 original + 2 imported
        assert len(rows) == 4
        imported_scoped = [r for r in rows if r["name"] == "P"]
        preset_ids = {r["id"] for r in await _read_db(tmp_test_dir, "SELECT id FROM presets")}
        for row in imported_scoped:
            assert row["scope_id"] in preset_ids
