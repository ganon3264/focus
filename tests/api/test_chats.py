import aiosqlite

from tests.helpers import create_character, create_chat, create_persona, create_preset


class TestChats:
    async def test_create_empty(self, client):
        resp = await client.post("/api/chats/", json={})
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
        old = await create_chat(client)
        fresh = await create_chat(client)
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


class TestChatSearch:
    async def _seed(self, db_path, chat_id, content, role="assistant", active=0, variant_index=0):
        import uuid
        from datetime import UTC, datetime

        now = datetime.now(UTC).isoformat()
        msg_id = str(uuid.uuid4())
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (msg_id, chat_id, role, 1, active, now),
            )
            await db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), msg_id, variant_index, content, now),
            )
            await db.commit()
        return msg_id

    async def test_finds_the_active_variant_of_a_live_chat(self, client, tmp_test_dir):
        from tests.api.test_message_ops import _db_path

        chat = await create_chat(client)
        msg_id = await self._seed(_db_path(tmp_test_dir), chat["id"], "the rain smells of rust")

        resp = await client.get("/partials/chat-search?q=rust")

        assert resp.status_code == 200
        assert f"/chat/{chat['id']}?at={msg_id}" in resp.text
        assert "smells of <mark>rust</mark>" in resp.text
        assert 'data-search-count="1"' in resp.text
        assert 'data-search-max="40"' in resp.text

    async def test_ignores_an_inactive_variant(self, client, tmp_test_dir):
        import uuid
        from datetime import UTC, datetime

        from tests.api.test_message_ops import _db_path

        chat = await create_chat(client)
        db_path = _db_path(tmp_test_dir)
        msg_id = await self._seed(db_path, chat["id"], "the old take")
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), msg_id, 1, "the new take", datetime.now(UTC).isoformat()),
            )
            await db.execute("UPDATE messages SET active_index = 1 WHERE id = ?", (msg_id,))
            await db.commit()

        resp = await client.get("/partials/chat-search?q=take")

        assert "the new <mark>take</mark>" in resp.text
        assert "old" not in resp.text

    async def test_ignores_deleted_chats(self, client, tmp_test_dir):
        from tests.api.test_message_ops import _db_path

        chat = await create_chat(client)
        await self._seed(_db_path(tmp_test_dir), chat["id"], "buried treasure")
        await client.delete(f"/api/chats/{chat['id']}")

        resp = await client.get("/partials/chat-search?q=treasure")

        assert "No matches" in resp.text

    async def test_hit_names_its_character_and_persona(self, client, tmp_test_dir):
        from tests.api.test_message_ops import _db_path

        character = await create_character(client, "Alice")
        persona = await create_persona(client, "Kuon")
        chat = await create_chat(
            client, character_id=character["id"], persona_id=persona["id"]
        )
        await self._seed(_db_path(tmp_test_dir), chat["id"], "the keeper of keys")

        resp = await client.get("/partials/chat-search?q=keeper")

        assert 'class="search-hit-context">Alice · Kuon<' in resp.text

    async def test_hit_names_a_persona_without_a_character(self, client, tmp_test_dir):
        from tests.api.test_message_ops import _db_path

        persona = await create_persona(client, "Kuon")
        chat = await create_chat(client, persona_id=persona["id"])
        await self._seed(_db_path(tmp_test_dir), chat["id"], "the keeper of keys")

        resp = await client.get("/partials/chat-search?q=keeper")

        assert 'class="search-hit-context">Kuon<' in resp.text

    async def test_operators_are_neutralised(self, client, tmp_test_dir):
        from tests.api.test_message_ops import _db_path

        chat = await create_chat(client)
        await self._seed(_db_path(tmp_test_dir), chat["id"], "axb needs no percent sign")

        # FTS5 syntax in the box is text, not an operator: the quoting happens
        # server-side, so a stray quote or star is just a character.
        resp = await client.get('/partials/chat-search?q=percent%22*')

        assert resp.status_code == 200
        assert "no <mark>percent</mark> sign" in resp.text


async def test_search_scope_can_be_one_character(client, tmp_test_dir):
    from tests.api.test_message_ops import _db_path

    db_path = _db_path(tmp_test_dir)
    one = await create_character(client, "One")
    two = await create_character(client, "Two")
    chat_one = await create_chat(client, character_id=one["id"])
    chat_two = await create_chat(client, character_id=two["id"])
    seeder = TestChatSearch()
    await seeder._seed(db_path, chat_one["id"], "the keeper of keys")
    await seeder._seed(db_path, chat_two["id"], "the keeper of doors")

    scoped = await client.get(f"/partials/chat-search?q=keeper&character_id={one['id']}")
    wide = await client.get("/partials/chat-search?q=keeper")

    assert "keys" in scoped.text and "doors" not in scoped.text
    assert "keys" in wide.text and "doors" in wide.text
