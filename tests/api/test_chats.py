from tests.helpers import create_character, create_chat, create_persona, create_preset

import aiosqlite


class TestChats:
    async def test_create_empty(self, client):
        resp = await client.post("/api/chats/", json={"title": "Empty"})
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_create_with_entities(self, client):
        c = await create_character(client, "Char")
        p = await create_persona(client, "Persona")
        pr = await create_preset(client, "Preset")
        resp = await client.post(
            "/api/chats/",
            json={
                "character_id": c["id"],
                "persona_id": p["id"],
                "preset_id": pr["id"],
            },
        )
        assert resp.status_code == 201

    async def test_list(self, client):
        await create_chat(client)
        resp = await client.get("/api/chats/")
        assert len(resp.json()) >= 1

    async def test_get_by_id(self, client):
        c = await create_character(client, "Char")
        ch = await create_chat(client, character_id=c["id"])
        resp = await client.get(f"/api/chats/{ch['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["character_id"] == c["id"]
        assert "messages" in data

    async def test_update_title(self, client):
        ch = await create_chat(client)
        await client.patch(f"/api/chats/{ch['id']}", json={"title": "New Title"})
        resp = await client.get(f"/api/chats/{ch['id']}")
        assert resp.json()["title"] == "New Title"

    async def test_delete(self, client):
        ch = await create_chat(client)
        await client.delete(f"/api/chats/{ch['id']}")

        resp = await client.get(f"/api/chats/{ch['id']}")
        assert resp.status_code == 404

    async def test_get_not_found(self, client):
        resp = await client.get("/api/chats/nope")
        assert resp.status_code == 404

    async def test_update_chat_character(self, client):
        c1 = await create_character(client, "First")
        c2 = await create_character(client, "Second")
        ch = await create_chat(client, character_id=c1["id"])

        await client.patch(f"/api/chats/{ch['id']}", json={"character_id": c2["id"]})
        resp = await client.get(f"/api/chats/{ch['id']}")
        assert resp.json()["character_id"] == c2["id"]


class TestStaleChats:
    async def _age(self, tmp_test_dir, chat_id, days):
        import os
        from datetime import UTC, datetime, timedelta

        async with aiosqlite.connect(os.path.join(tmp_test_dir, "test.db")) as db:
            await db.execute(
                "UPDATE chats SET updated_at = ? WHERE id = ?",
                ((datetime.now(UTC) - timedelta(days=days)).isoformat(), chat_id),
            )
            await db.commit()

    async def test_count_and_trash(self, client, tmp_test_dir):
        old = await create_chat(client, title="Old")
        fresh = await create_chat(client, title="Fresh")
        await self._age(tmp_test_dir, old["id"], 40)

        count = await client.get("/api/chats/stale?days=30")
        assert count.json()["count"] == 1

        resp = await client.delete("/api/chats/stale?days=30")
        assert resp.json() == {"deleted": 1, "ids": [old["id"]]}

        assert (await client.get(f"/api/chats/{old['id']}")).status_code == 404
        assert (await client.get(f"/api/chats/{fresh['id']}")).status_code == 200

        trash = [c["id"] for c in (await client.get("/api/chats/trash")).json()]
        assert old["id"] in trash

        restored = await client.post(f"/api/chats/{old['id']}/restore")
        assert restored.status_code == 200
        assert (await client.get(f"/api/chats/{old['id']}")).status_code == 200

    async def test_nothing_old_enough(self, client, tmp_test_dir):
        ch = await create_chat(client)
        await self._age(tmp_test_dir, ch["id"], 5)

        assert (await client.get("/api/chats/stale?days=30")).json()["count"] == 0
        assert (await client.delete("/api/chats/stale?days=30")).json()["deleted"] == 0
        assert (await client.get(f"/api/chats/{ch['id']}")).status_code == 200

    async def test_rejects_zero_days(self, client):
        assert (await client.get("/api/chats/stale?days=0")).status_code == 422
        assert (await client.delete("/api/chats/stale?days=0")).status_code == 422
        assert (await client.delete("/api/chats/stale?days=999999")).status_code == 422

    async def test_skips_already_trashed(self, client, tmp_test_dir):
        ch = await create_chat(client)
        await self._age(tmp_test_dir, ch["id"], 40)
        await client.delete(f"/api/chats/{ch['id']}")

        assert (await client.get("/api/chats/stale?days=30")).json()["count"] == 0


class TestCrossEntity:
    async def test_chat_with_character_no_greetings(self, client):
        c = await create_character(client, "Bot")
        resp = await client.post("/api/chats/", json={"character_id": c["id"]})
        ch = await client.get(f"/api/chats/{resp.json()['id']}")
        assert len(ch.json()["messages"]) == 0

    async def test_chat_switch_persona(self, client):
        p1 = await create_persona(client, "P1")
        p2 = await create_persona(client, "P2")
        ch = await create_chat(client, persona_id=p1["id"])

        await client.patch(f"/api/chats/{ch['id']}", json={"persona_id": p2["id"]})
        resp = await client.get(f"/api/chats/{ch['id']}")
        assert resp.json()["persona_id"] == p2["id"]

    async def test_character_delete_orphans_chats(self, client):
        c = await create_character(client, "Fading")
        ch = await create_chat(client, character_id=c["id"])

        await client.delete(f"/api/characters/{c['id']}?hard=true")

        resp = await client.get(f"/api/chats/{ch['id']}")
        assert resp.status_code == 200
        assert resp.json()["character_id"] is None
