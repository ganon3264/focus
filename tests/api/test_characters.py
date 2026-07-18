from tests.helpers import create_character, create_chat


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


class TestCharacterLifecycle:
    async def test_set_character_on_chat(self, client):
        ch = await create_chat(client)
        c = await create_character(client, "Alice")

        resp = await client.patch(f"/api/chats/{ch['id']}", json={"character_id": c["id"]})
        assert resp.status_code == 200

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["character_id"] == c["id"]

    async def test_hard_delete_character_orphans_chat(self, client):
        c = await create_character(client, "Bob")
        ch = await create_chat(client, character_id=c["id"])

        await client.delete(f"/api/characters/{c['id']}?hard=true")

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["character_id"] is None


class TestCharacterModals:
    async def test_modal_highlights_current(self, client):
        c1 = await create_character(client, "Alice")
        c2 = await create_character(client, "Bob")

        resp = await client.get(f"/partials/characters-modal?current_character_id={c1['id']}")
        assert resp.status_code == 200
        html = resp.text

        assert 'class="card active"' in html
        assert f'id="char-card-{c1["id"]}"' in html
        assert f'id="char-card-{c2["id"]}"' in html

    async def test_modal_no_current_no_highlight(self, client):
        await create_character(client, "Alice")
        resp = await client.get("/partials/characters-modal")
        assert resp.status_code == 200
        assert 'class="card active"' not in resp.text
