from tests.helpers import create_chat, create_preset


class TestPresets:
    async def test_create(self, client):
        resp = await client.post("/api/presets/", data={"name": "My Preset"})
        assert resp.status_code == 201
        assert "id" in resp.json()

    async def test_create_seeds_default_blocks(self, client):
        resp = await client.post("/api/presets/", data={"name": "Defaulted"})
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


class TestPresetLifecycle:
    async def test_set_preset_on_chat(self, client):
        ch = await create_chat(client)
        pr = await create_preset(client, "TestPreset")

        resp = await client.patch(f"/api/chats/{ch['id']}", json={"preset_id": pr["id"]})
        assert resp.status_code == 200

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["preset_id"] == pr["id"]

    async def test_clear_preset_on_chat(self, client):
        pr = await create_preset(client, "TestPreset")
        ch = await create_chat(client, preset_id=pr["id"])

        resp = await client.patch(f"/api/chats/{ch['id']}", json={"preset_id": None})
        assert resp.status_code == 200

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["preset_id"] is None

    async def test_delete_preset_clears_chat_preset_id(self, client):
        pr = await create_preset(client, "TestPreset")
        ch = await create_chat(client, preset_id=pr["id"])

        await client.delete(f"/api/presets/{pr['id']}")

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["preset_id"] is None

    async def test_delete_cascades_blocks(self, client):
        pr = await create_preset(client, "TestPreset")
        presets = await client.get(f"/api/presets/{pr['id']}")
        assert len(presets.json()["blocks"]) >= 1

        await client.delete(f"/api/presets/{pr['id']}")

        resp = await client.get(f"/api/presets/{pr['id']}")
        assert resp.status_code == 404
