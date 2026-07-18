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
