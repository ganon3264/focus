"""Integration tests for the FastAPI endpoints using a test database."""

from tests.conftest import create_character, create_chat, create_persona, create_preset

class TestCharacters:
    async def test_list_empty(self, client):
        resp = await client.get("/api/characters/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create(self, client):
        resp = await client.post(
            "/api/characters/",
            json={
                "name": "Sylvie",
                "description": "A fox",
                "personality": "Clever",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == "Sylvie"

    async def test_list_after_create(self, client):
        await create_character(client, "A")
        await create_character(client, "B")
        resp = await client.get("/api/characters/")
        assert len(resp.json()) == 2

    async def test_get_by_id(self, client):
        c = await create_character(client, "Char1", description="Test desc")
        resp = await client.get(f"/api/characters/{c['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Char1"
        card = data["card"]
        assert card["data"]["description"] == "Test desc"

    async def test_get_not_found(self, client):
        resp = await client.get("/api/characters/nonexistent")
        assert resp.status_code == 404

    async def test_update(self, client):
        c = await create_character(client, "Original")
        await client.patch(
            f"/api/characters/{c['id']}",
            json={
                "name": "Renamed",
                "personality": "Grumpy",
            },
        )
        resp = await client.get(f"/api/characters/{c['id']}")
        card = resp.json()["card"]
        assert card["data"]["name"] == "Renamed"
        assert card["data"]["personality"] == "Grumpy"
        assert card["data"]["description"] == "Desc"

    async def test_soft_delete_and_trash(self, client):
        c = await create_character(client, "Deletable")
        await client.delete(f"/api/characters/{c['id']}")

        resp = await client.get("/api/characters/")
        assert len(resp.json()) == 0

        resp = await client.get("/api/characters/trash")
        assert len(resp.json()) == 1

    async def test_restore(self, client):
        c = await create_character(client, "Restorable")
        await client.delete(f"/api/characters/{c['id']}")
        await client.post(f"/api/characters/{c['id']}/restore")

        resp = await client.get("/api/characters/")
        assert len(resp.json()) == 1

    async def test_hard_delete(self, client):
        c = await create_character(client, "HardDelete")
        await client.delete(f"/api/characters/{c['id']}?hard=true")

        resp = await client.get(f"/api/characters/{c['id']}")
        assert resp.status_code == 404

class TestPersonas:
    async def test_list(self, client):
        resp = await client.get("/api/personas/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_create(self, client):
        resp = await client.post("/api/personas/", json={"name": "Hero", "description": "Brave"})
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_get_by_id(self, client):
        p = await create_persona(client, "Tester")
        resp = await client.get(f"/api/personas/{p['id']}")
        assert resp.status_code == 200
        assert resp.json()["name"] == "Tester"

    async def test_update(self, client):
        p = await create_persona(client, "Old")
        await client.patch(f"/api/personas/{p['id']}", json={"name": "New"})
        resp = await client.get(f"/api/personas/{p['id']}")
        assert resp.json()["name"] == "New"

    async def test_delete(self, client):
        p = await create_persona(client, "Doomed")
        await client.delete(f"/api/personas/{p['id']}")

        resp = await client.get(f"/api/personas/{p['id']}")
        assert resp.status_code == 404

    async def test_get_not_found(self, client):
        resp = await client.get("/api/personas/nope")
        assert resp.status_code == 404

class TestPresets:
    async def test_create(self, client):
        resp = await client.post("/api/presets/", json={"name": "My Preset"})
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_create_seeds_default_blocks(self, client):
        resp = await client.post("/api/presets/", json={"name": "Defaulted"})
        preset = await client.get(f"/api/presets/{resp.json()['id']}")
        blocks = preset.json()["blocks"]
        types = {b["block_type"] for b in blocks}
        assert "text" in types
        assert "char_description" in types
        assert "user_persona" in types

    async def test_list(self, client):
        await create_preset(client, "P1")
        resp = await client.get("/api/presets/")
        assert len(resp.json()) >= 1

    async def test_get_by_id(self, client):
        p = await create_preset(client, "Detail")
        resp = await client.get(f"/api/presets/{p['id']}")
        assert resp.json()["name"] == "Detail"
        assert "blocks" in resp.json()

    async def test_rename(self, client):
        p = await create_preset(client, "Old")
        await client.patch(f"/api/presets/{p['id']}", json={"name": "New"})
        resp = await client.get(f"/api/presets/{p['id']}")
        assert resp.json()["name"] == "New"

    async def test_delete(self, client):
        p = await create_preset(client, "Doomed")
        resp = await client.delete(f"/api/presets/{p['id']}")
        assert resp.status_code == 204

        resp = await client.get(f"/api/presets/{p['id']}")
        assert resp.status_code == 404

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

class TestProviders:
    async def test_list_empty(self, client):
        resp = await client.get("/api/providers/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create(self, client):
        resp = await client.post(
            "/api/providers/",
            json={
                "name": "Test",
                "type": "openai_compat",
                "model": "gpt-4",
                "api_key": "sk-test",
            },
        )
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_list_single(self, client):
        await client.post(
            "/api/providers/",
            json={
                "name": "P1",
                "type": "openai_compat",
                "model": "gpt-4",
            },
        )
        resp = await client.get("/api/providers/")
        providers = resp.json()
        assert len(providers) == 1
        assert providers[0]["name"] == "P1"

    async def test_update(self, client):
        resp = await client.post(
            "/api/providers/",
            json={
                "name": "Old",
                "type": "openai_compat",
                "model": "gpt-4",
            },
        )
        pid = resp.json()["id"]

        await client.patch(f"/api/providers/{pid}", json={"name": "New", "model": "gpt-4-turbo"})
        resp = await client.get("/api/providers/")
        p = resp.json()[0]
        assert p["name"] == "New"
        assert p["model"] == "gpt-4-turbo"

    async def test_delete(self, client):
        resp = await client.post(
            "/api/providers/",
            json={
                "name": "Del",
                "type": "openai_compat",
                "model": "gpt-4",
            },
        )
        pid = resp.json()["id"]

        await client.delete(f"/api/providers/{pid}")
        resp = await client.get("/api/providers/")
        assert resp.json() == []

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

    async def test_preset_delete_cascades_blocks(self, client):
        p = await create_preset(client, "Doomed")
        resp = await client.get(f"/api/presets/{p['id']}")
        assert len(resp.json()["blocks"]) > 0

        await client.delete(f"/api/presets/{p['id']}")
        resp = await client.get(f"/api/presets/{p['id']}")
        assert resp.status_code == 404

    async def test_character_delete_orphans_chats(self, client):
        c = await create_character(client, "Fading")
        ch = await create_chat(client, character_id=c["id"])

        await client.delete(f"/api/characters/{c['id']}?hard=true")

        resp = await client.get(f"/api/chats/{ch['id']}")
        assert resp.status_code == 200
        assert resp.json()["character_id"] is None
