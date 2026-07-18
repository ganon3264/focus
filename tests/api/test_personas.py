from tests.helpers import create_chat, create_persona


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


class TestPersonaLifecycle:
    async def test_set_persona_on_chat(self, client):
        ch = await create_chat(client)
        p = await create_persona(client, "MyPersona")

        resp = await client.patch(f"/api/chats/{ch['id']}", json={"persona_id": p["id"]})
        assert resp.status_code == 200

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["persona_id"] == p["id"]


class TestPersonaModals:
    async def test_modal_highlights_current(self, client):
        p1 = await create_persona(client, "PersonaOne")
        p2 = await create_persona(client, "PersonaTwo")

        resp = await client.get(f"/partials/personas-modal?current_persona_id={p1['id']}")
        assert resp.status_code == 200
        html = resp.text

        assert 'class="card active"' in html
        assert f'id="persona-card-{p1["id"]}"' in html
        assert f'id="persona-card-{p2["id"]}"' in html
