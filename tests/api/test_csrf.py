"""Tests for the cross-origin (CSRF) request middleware."""

from io import BytesIO


class TestOriginCheck:
    async def test_mismatched_origin_rejected(self, client):
        resp = await client.post(
            "/api/chats/",
            json={"title": "x"},
            headers={"Origin": "http://evil.example"},
        )
        assert resp.status_code == 403

    async def test_multipart_import_with_mismatched_origin_rejected(self, client):
        files = {"file": ("x.focus", BytesIO(b"garbage"), "application/zip")}
        resp = await client.post(
            "/api/import",
            files=files,
            headers={"Origin": "http://evil.example"},
        )
        assert resp.status_code == 403

    async def test_mismatched_origin_with_port_rejected(self, client):
        resp = await client.post(
            "/api/chats/",
            json={"title": "x"},
            headers={"Origin": "http://test:9999"},
        )
        assert resp.status_code == 403

    async def test_same_origin_allowed(self, client):
        resp = await client.post(
            "/api/chats/",
            json={"title": "x"},
            headers={"Origin": "http://test"},
        )
        assert resp.status_code == 201

    async def test_missing_origin_allowed(self, client):
        resp = await client.post("/api/chats/", json={"title": "x"})
        assert resp.status_code == 201

    async def test_get_with_foreign_origin_allowed(self, client):
        resp = await client.get("/api/chats/", headers={"Origin": "http://evil.example"})
        assert resp.status_code == 200
