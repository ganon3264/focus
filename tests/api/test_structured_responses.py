from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from io import BytesIO
from zipfile import ZipFile

import aiosqlite
import pytest

from tests.api.test_stream_generation import (
    FakeProvider,
    _assistant_variant,
    _consume_sse_events,
    _db_path,
    _fetchone,
    _now_iso,
    _stream,
)
from tests.helpers import create_character, create_chat, create_persona, create_preset

SCHEMA = (
    '{"type":"object","properties":{"text":{"type":"string"}},'
    '"required":["text"],"additionalProperties":false}'
)


def _new_response(**overrides) -> dict:
    body = {
        "scope": "global",
        "name": "Response",
        "json_schema": SCHEMA,
        "template": "{{{text}}}",
        "enabled": True,
    }
    body.update(overrides)
    return body


async def _setup(client):
    char = await create_character(client, "Char")
    persona = await create_persona(client, "P")
    preset = await create_preset(client, "Pr")
    chat = await create_chat(client, char["id"], persona["id"], preset["id"])
    resp = await client.post(
        "/api/providers/",
        json={"name": "TestProvider", "type": "openai_compat", "model": "gpt-4"},
    )
    assert resp.status_code == 201
    return chat, preset["id"], resp.json()["id"]


@pytest.fixture
def patch_provider(monkeypatch):
    """Redirect provider construction to a fake for the duration of a test."""

    def _patch(provider):
        import focus.providers as providers_mod
        from focus.routers import stream as stream_module

        monkeypatch.setattr(providers_mod, "create_provider", lambda row: provider)
        monkeypatch.setattr(stream_module, "create_provider", lambda row: provider)

    return _patch


async def _read_db(tmp_test_dir, sql: str, params: tuple = ()):
    db_path = os.path.join(tmp_test_dir, "test.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        return await cur.fetchall()


class TestCrud:
    async def test_create_and_list_global(self, client):
        resp = await client.post("/api/structured-responses", json=_new_response())
        assert resp.status_code == 201
        created = resp.json()
        assert created["scope"] == "global"
        assert created["enabled"] is True

        listing = (await client.get("/api/structured-responses")).json()
        assert [r["id"] for r in listing["responses"]] == [created["id"]]

    async def test_preset_requires_scope_id(self, client):
        resp = await client.post(
            "/api/structured-responses", json=_new_response(scope="preset")
        )
        assert resp.status_code == 400

    async def test_list_with_preset_includes_global_first(self, client):
        preset = await create_preset(client)
        await client.post("/api/structured-responses", json=_new_response(name="G"))
        await client.post(
            "/api/structured-responses",
            json=_new_response(scope="preset", scope_id=preset["id"], name="P"),
        )
        listing = (
            await client.get(f"/api/structured-responses?preset_id={preset['id']}")
        ).json()
        assert [r["name"] for r in listing["responses"]] == ["G", "P"]

    async def test_only_one_active_per_scope(self, client):
        first = (
            await client.post("/api/structured-responses", json=_new_response(name="A"))
        ).json()
        second = (
            await client.post("/api/structured-responses", json=_new_response(name="B"))
        ).json()

        listing = (await client.get("/api/structured-responses")).json()
        by_name = {r["name"]: r for r in listing["responses"]}
        assert by_name["A"]["enabled"] is False
        assert by_name["B"]["enabled"] is True
        assert first["id"] != second["id"]

    async def test_update_and_delete(self, client):
        created = (
            await client.post("/api/structured-responses", json=_new_response())
        ).json()
        resp = await client.patch(
            f"/api/structured-responses/{created['id']}",
            json={"template": "{{{text}}}!"},
        )
        assert resp.status_code == 200
        assert resp.json()["template"] == "{{{text}}}!"

        assert (
            await client.delete(f"/api/structured-responses/{created['id']}")
        ).status_code == 204
        assert (
            await client.delete(f"/api/structured-responses/{created['id']}")
        ).status_code == 404

    async def test_patch_scope_to_global_clears_scope_id(self, client):
        preset = await create_preset(client)
        created = (
            await client.post(
                "/api/structured-responses",
                json=_new_response(scope="preset", scope_id=preset["id"]),
            )
        ).json()
        resp = await client.patch(
            f"/api/structured-responses/{created['id']}", json={"scope": "global"}
        )
        assert resp.status_code == 200
        assert resp.json()["scope_id"] is None

    async def test_patch_scope_to_preset_requires_scope_id(self, client):
        created = (await client.post("/api/structured-responses", json=_new_response())).json()
        resp = await client.patch(
            f"/api/structured-responses/{created['id']}", json={"scope": "preset"}
        )
        assert resp.status_code == 400

    async def test_patch_ignores_explicit_nulls(self, client):
        created = (await client.post("/api/structured-responses", json=_new_response())).json()
        resp = await client.patch(
            f"/api/structured-responses/{created['id']}",
            json={"enabled": None, "name": None},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated["enabled"] is True
        assert updated["name"] == created["name"]

    async def test_invalid_schema_rejected_but_drafts_allowed(self, client):
        bad_schema = await client.post(
            "/api/structured-responses", json=_new_response(json_schema="{nope")
        )
        assert bad_schema.status_code == 400
        # Empty schema/template are drafts; generation skips them.
        draft = await client.post(
            "/api/structured-responses", json=_new_response(json_schema="", template="")
        )
        assert draft.status_code == 201


class TestPreview:
    async def test_preview_renders_template(self, client):
        resp = await client.post(
            "/api/structured-responses/preview",
            json={"template": "*{{{thought}}}* {{{text}}}", "json_sample": '{"thought":"hm","text":"hi"}'},
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "*hm* hi"

    async def test_preview_rejects_bad_sample(self, client):
        resp = await client.post(
            "/api/structured-responses/preview",
            json={"template": "{{{text}}}", "json_sample": "not json"},
        )
        assert resp.status_code == 400


class TestPartial:
    async def test_renders_groups(self, client):
        await client.post("/api/structured-responses", json=_new_response(name="Global set"))
        resp = await client.get("/partials/structured-responses")
        assert resp.status_code == 200
        assert "Global set" in resp.text
        assert "No global responses." not in resp.text
        assert "No responses for this preset." not in resp.text

    async def test_no_preset_hides_preset_group(self, client):
        resp = await client.get("/partials/structured-responses")
        assert "Select a preset" in resp.text


class TestExportRoundtrip:
    async def test_export_carries_global_and_scoped(self, client):
        preset = await create_preset(client)
        global_resp = (
            await client.post("/api/structured-responses", json=_new_response(name="G"))
        ).json()
        await client.post(
            "/api/structured-responses",
            json=_new_response(scope="preset", scope_id=preset["id"], name="P"),
        )

        resp = await client.post("/api/export", json={"presets": [preset["id"]]})
        with ZipFile(BytesIO(resp.content)) as zf:
            db = json.loads(zf.read("database.json"))

        responses = {r["name"]: r for r in db["structured_responses"]}
        assert set(responses) == {"G", "P"}
        assert responses["G"]["scope_id"] is None
        assert responses["P"]["scope_id"] == db["presets"][0]["id"]
        assert responses["P"]["scope_id"] != preset["id"]
        assert responses["G"]["id"] != global_resp["id"]

    async def test_import_restores_responses(self, client, tmp_test_dir):
        preset = await create_preset(client)
        await client.post("/api/structured-responses", json=_new_response(name="G"))
        await client.post(
            "/api/structured-responses",
            json=_new_response(scope="preset", scope_id=preset["id"], name="P"),
        )

        exported = (await client.post("/api/export", json={"presets": [preset["id"]]})).content
        files = {"file": ("x.focus", BytesIO(exported), "application/zip")}
        imp = await client.post("/api/import", files=files)
        assert imp.status_code == 201

        rows = await _read_db(
            tmp_test_dir, "SELECT name, scope, scope_id FROM structured_responses"
        )
        names = {r["name"] for r in rows}
        assert {"G", "P"} <= names
        preset_ids = {r["id"] for r in await _read_db(tmp_test_dir, "SELECT id FROM presets")}
        for row in [r for r in rows if r["name"] == "P"]:
            assert row["scope_id"] in preset_ids


class TestStructuredThenBlockRegex:
    async def test_block_extracts_structured_think(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, preset_id, prov_id = await _setup(client)
        await client.post(
            "/api/structured-responses",
            json=_new_response(scope="preset", scope_id=preset_id),
        )
        await client.post(
            "/api/regex-scripts",
            json={
                "scope": "global",
                "name": "Think",
                "pattern": r"<think>(.*?)</think>",
                "flags": "s",
                "replacement": "",
                "placement": "ai",
                "apply_prompt": True,
                "apply_display": True,
                "as_block": True,
            },
        )
        payload = json.dumps({"text": "<think>\nsecret\n</think>\nreply"})
        fake = FakeProvider([[
            {"type": "token", "text": payload},
            {"type": "done"},
        ]])
        patch_provider(fake)

        resp = await client.post(
            "/api/stream",
            json={
                "chat_id": chat["id"],
                "provider_id": prov_id,
                "user_message": "Hi",
                "samplers": {"stream_enabled": True},
                "regenerate": False,
                "attachment_ids": [],
                "tools_enabled": False,
                "tool_read_only": True,
            },
        )
        assert resp.status_code == 200

        html = (await client.get(f"/partials/message-list/{chat['id']}")).text
        assert "<summary>" in html
        assert "Think" in html
        assert "secret" in html
        assert "reply" in html


class TestGeneration:
    async def test_structured_generation_renders_and_buffers(self, client, tmp_test_dir, patch_provider):
        chat, preset_id, prov_id = await _setup(client)
        await client.post(
            "/api/structured-responses",
            json=_new_response(
                scope="preset",
                scope_id=preset_id,
                name="Response",
                template="*{{{thought}}}*\n{{{text}}}",
            ),
        )
        fake = FakeProvider([
            [
                {"type": "token", "text": '{"thought":"hmm","text":"Hello"}'},
                {"type": "done"},
            ],
        ])
        patch_provider(fake)

        resp = await client.post(
            "/api/stream",
            json={
                "chat_id": chat["id"],
                "provider_id": prov_id,
                "user_message": "Hi",
                "samplers": {"stream_enabled": True},
                "regenerate": False,
                "attachment_ids": [],
                "tools_enabled": False,
                "tool_read_only": True,
            },
        )
        assert resp.status_code == 200
        events = await _consume_sse_events(resp)
        tokens = [e["text"] for e in events if e.get("type") == "token"]
        # Buffered: exactly one token, already templated (no raw JSON).
        assert tokens == ["*hmm*\nHello"]

        kwargs = fake.all_kwargs[0]
        assert kwargs["stream"] is False
        assert kwargs["response_format"]["json_schema"]["schema"]["type"] == "object"

        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        assert asst["content"] == "*hmm*\nHello"

    async def test_render_failure_aborts_and_rolls_back(self, client, tmp_test_dir, patch_provider):
        chat, preset_id, prov_id = await _setup(client)
        await client.post(
            "/api/structured-responses",
            json=_new_response(scope="preset", scope_id=preset_id),
        )
        fake = FakeProvider([
            [
                {"type": "token", "text": "not json at all"},
                {"type": "done"},
            ],
        ])
        patch_provider(fake)

        resp = await client.post(
            "/api/stream",
            json={
                "chat_id": chat["id"],
                "provider_id": prov_id,
                "user_message": "Hi",
                "samplers": {"stream_enabled": True},
                "regenerate": False,
                "attachment_ids": [],
                "tools_enabled": False,
                "tool_read_only": True,
            },
        )
        events = await _consume_sse_events(resp)
        assert any(e.get("type") == "error" for e in events)
        assert not any(e.get("type") == "done" for e in events)
        assert await _assistant_variant(_db_path(tmp_test_dir), chat["id"]) is None

    async def test_stop_before_first_token_finalizes_as_stop(
        self, client, tmp_test_dir, patch_provider
    ):
        """A user stop in buffered mode arrives as ``done`` with nothing
        accumulated; it must finalize as a normal stop, not surface a JSON
        parse failure."""
        chat, preset_id, prov_id = await _setup(client)
        await client.post(
            "/api/structured-responses",
            json=_new_response(scope="preset", scope_id=preset_id),
        )
        started = asyncio.Event()
        release = asyncio.Event()

        class GatedProvider(FakeProvider):
            async def stream_complete(self, messages, **kwargs):
                started.set()
                await release.wait()
                yield {"type": "token", "text": '{"text":"hi"}'}
                yield {"type": "done"}

        patch_provider(GatedProvider([]))

        task = asyncio.create_task(_stream(client, chat["id"], prov_id))
        await asyncio.wait_for(started.wait(), 10)

        db_path = _db_path(tmp_test_dir)
        deadline = time.monotonic() + 5
        asst_id = None
        while time.monotonic() < deadline:
            row = await _fetchone(
                db_path,
                "SELECT id FROM messages WHERE chat_id = ? AND role = 'assistant' AND position > 0",
                chat["id"],
            )
            if row:
                asst_id = row[0]
                break
            await asyncio.sleep(0.01)
        assert asst_id, "assistant slot must exist while generation is in flight"

        stop_resp = await client.post(f"/api/stop-generation/{asst_id}")
        assert stop_resp.status_code == 200

        release.set()
        resp = await asyncio.wait_for(task, 10)
        events = await _consume_sse_events(resp)
        assert events[0]["type"] == "start"
        assert events[-1]["type"] == "done"
        assert not any(e.get("type") == "error" for e in events)
        assert await _assistant_variant(db_path, chat["id"]) is None

    async def test_continue_disables_structured(self, client, tmp_test_dir, patch_provider):
        """Continue streams into an existing variant, so the JSON-render path
        must be skipped: no response_format, raw text stored as-is."""
        chat, preset_id, prov_id = await _setup(client)
        await client.post(
            "/api/structured-responses",
            json=_new_response(scope="preset", scope_id=preset_id),
        )
        db_path = _db_path(tmp_test_dir)
        now = _now_iso()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), chat["id"], "user", 0, 0, now),
            )
            asst_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (asst_id, chat["id"], "assistant", 1, 0, now),
            )
            await db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), asst_id, 0, "Old text", now),
            )
            await db.commit()

        fake = FakeProvider(
            [[{"type": "token", "text": " rest"}, {"type": "done"}]],
            echoes_prefill=False,
        )
        patch_provider(fake)

        resp = await _stream(
            client, chat["id"], prov_id,
            user_message="",
            regenerate=True,
            continue_text="cont",
        )
        events = await _consume_sse_events(resp)
        assert "response_format" not in fake.all_kwargs[0]
        tokens = [e["text"] for e in events if e.get("type") == "token"]
        assert tokens == ["cont", " rest"], "raw text, no template render"
        asst = await _assistant_variant(db_path, chat["id"])
        assert asst["content"] == "cont rest"
