import asyncio
import os

import aiosqlite

from tests.helpers import create_character, create_chat, create_persona


class _FakeProvider:
    supports_prefill = True
    echoes_prefill = True
    supports_tools = True

    def __init__(self, events):
        self.events = list(events)
        self.calls = 0

    async def stream_complete(self, messages, **kwargs):
        self.calls += 1
        for e in self.events:
            yield e


def _db_path(tmp_test_dir):
    return os.path.join(tmp_test_dir, "test.db")


async def _assistant_variants(db_path, chat_id):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT mv.content FROM message_variants mv "
            "JOIN messages m ON mv.message_id = m.id "
            "WHERE m.chat_id = ? AND m.role = 'assistant' "
            "ORDER BY mv.variant_index",
            (chat_id,),
        )
        return [dict(r) for r in await cur.fetchall()]


class TestExtensionsApi:
    async def test_create_swipe_rewrite(self, client):
        char = await create_character(client, "Char", first_mes="Hello world")
        chat = await create_chat(client, character_id=char["id"])

        resp = await client.get(f"/api/chats/{chat['id']}")
        messages = resp.json()["messages"]
        assert len(messages) == 1
        msg = messages[0]
        assert msg["role"] == "assistant"

        # Enable the caps_rewrite extension for this chat, then run it.
        resp = await client.put(
            f"/api/chats/{chat['id']}/extensions",
            json={"states": {"caps_rewrite": True}},
        )
        assert resp.status_code == 200

        resp = await client.post(
            "/api/extensions/caps_rewrite/run",
            json={"chat_id": chat["id"], "message_id": msg["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["swipe_created"] is True
        assert data["variant_index"] == 1
        assert data["status"] == "done"

        # The rewritten content is now the active variant (a new swipe).
        resp = await client.get(f"/api/chats/{chat['id']}/messages/{msg['id']}")
        assert resp.json()["content"] == "HELLO WORLD"

    async def test_read_text_returns_content(self, client):
        char = await create_character(client, "Char", first_mes="Speak this")
        chat = await create_chat(client, character_id=char["id"])
        msg = (await client.get(f"/api/chats/{chat['id']}")).json()["messages"][0]

        resp = await client.post(
            "/api/extensions/read_text/run",
            json={"chat_id": chat["id"], "message_id": msg["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["swipe_created"] is False
        assert data["content"] == "Speak this"
        assert data["status"] == "done"

    async def test_attach_file(self, client):
        char = await create_character(client, "Char", first_mes="hi")
        chat = await create_chat(client, character_id=char["id"])
        msg = (await client.get(f"/api/chats/{chat['id']}")).json()["messages"][0]

        resp = await client.post(
            "/api/extensions/attach_note/run",
            json={"chat_id": chat["id"], "message_id": msg["id"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["attachments_added"] == 1
        assert data["swipe_created"] is False

        got = await client.get(f"/api/chats/{chat['id']}/messages/{msg['id']}")
        assert len(got.json()["attachments"]) == 1
        assert got.json()["attachments"][0]["mime_type"] == "text/plain"

    async def test_list_extensions(self, client):
        resp = await client.get("/api/extensions")
        assert resp.status_code == 200
        names = {e["name"] for e in resp.json()}
        assert "caps_rewrite" in names
        assert "read_text" in names

    async def test_enable_state_round_trip(self, client):
        char = await create_character(client, "Char")
        chat = await create_chat(client, character_id=char["id"])
        await client.put(
            f"/api/chats/{chat['id']}/extensions",
            json={"states": {"read_text": True, "caps_rewrite": False}},
        )
        resp = await client.get(f"/api/chats/{chat['id']}/extensions")
        states = resp.json()["states"]
        assert states["read_text"] is True
        assert states["caps_rewrite"] is False

    async def test_run_unknown_extension_404(self, client):
        char = await create_character(client, "Char", first_mes="hi")
        chat = await create_chat(client, character_id=char["id"])
        msg = (await client.get(f"/api/chats/{chat['id']}")).json()["messages"][0]
        resp = await client.post(
            "/api/extensions/nope/run",
            json={"chat_id": chat["id"], "message_id": msg["id"]},
        )
        assert resp.status_code == 404

    async def test_generation_end_trigger_auto_rewrites(self, client, tmp_test_dir, monkeypatch):
        char = await create_character(client, "Char")
        persona = await create_persona(client, "P")
        chat = await create_chat(client, character_id=char["id"], persona_id=persona["id"])
        resp = await client.post(
            "/api/providers/", json={"name": "T", "type": "openai_compat", "model": "m"}
        )
        prov_id = resp.json()["id"]

        # Enable caps_rewrite (it subscribes to generation_end) for this chat.
        await client.put(
            f"/api/chats/{chat['id']}/extensions",
            json={"states": {"caps_rewrite": True}},
        )

        fake = _FakeProvider([
            {"type": "token", "text": "Hello"},
            {"type": "usage", "usage": {
                "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2,
                "cached_tokens": 0, "reasoning_tokens": 0,
            }},
            {"type": "done"},
        ])
        import focus.providers as providers_mod
        from focus.routers import stream as stream_module
        monkeypatch.setattr(providers_mod, "create_provider", lambda row: fake)
        monkeypatch.setattr(stream_module, "create_provider", lambda row: fake)

        resp = await client.post("/api/stream", json={
            "chat_id": chat["id"], "provider_id": prov_id, "user_message": "hi",
            "samplers": {"stream_enabled": True}, "regenerate": False, "attachment_ids": [],
            "tools_enabled": False, "tool_read_only": True,
        })
        assert resp.status_code == 200

        # The generation_end trigger runs in the background; poll for the swipe.
        variants = []
        for _ in range(60):
            await asyncio.sleep(0.05)
            variants = await _assistant_variants(_db_path(tmp_test_dir), chat["id"])
            if len(variants) >= 2:
                break
        assert len(variants) == 2, f"expected original + rewritten variant, got {variants}"
        assert variants[0]["content"] == "Hello"
        assert variants[1]["content"] == "HELLO"


