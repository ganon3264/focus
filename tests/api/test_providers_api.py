"""API tests for the provider router (focus/routers/providers.py).

fetch_models / endpoints / balance / modalities hit HTTP endpoints, which
are mocked with httpx.MockTransport (patching httpx.AsyncClient globally).
Module-level TTL caches are cleared per test to keep tests independent.
"""

import json
from pathlib import Path

import aiosqlite
import httpx
import pytest


@pytest.fixture(autouse=True)
def _clear_provider_caches():
    import focus.routers.providers as p

    for cache in (p._model_cache, p._or_cache, p._balance_cache):
        cache._data.clear()
        cache._times.clear()


def _patch_httpx(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(
        httpx, "AsyncClient",
        lambda *a, **k: real(transport=httpx.MockTransport(handler)),
    )


async def _make_provider(client, ptype="openai_compat", api_key=None, model="m"):
    body = {"name": "P", "type": ptype, "model": model}
    if api_key is not None:
        body["api_key"] = api_key
    resp = await client.post("/api/providers/", json=body)
    assert resp.status_code == 201
    return resp.json()["id"]


class TestFetchModels:
    async def test_fetch_and_sort(self, client, monkeypatch):
        def handler(request):
            return httpx.Response(200, json={"data": [
                {"id": "z-model", "name": "Zed"},
                {"id": "a-model", "name": "Alpha", "context_length": 8192, "pricing": {"prompt": "0.1"}},
            ]})

        _patch_httpx(monkeypatch, handler)
        resp = await client.post(
            "/api/providers/fetch_models",
            json={"type": "openai_compat", "base_url": "http://example.com", "api_key": "sk-x"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert [m["id"] for m in data] == ["a-model", "z-model"]
        assert data[0]["context_length"] == 8192
        assert data[0]["pricing"] == {"prompt": "0.1"}

    async def test_cached_second_call(self, client, monkeypatch):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json={"data": [{"id": "m1"}]})

        _patch_httpx(monkeypatch, handler)
        body = {"type": "openai_compat", "base_url": "http://example.com", "api_key": "sk-same"}
        assert (await client.post("/api/providers/fetch_models", json=body)).status_code == 200
        assert (await client.post("/api/providers/fetch_models", json=body)).status_code == 200
        assert calls["n"] == 1

    async def test_api_key_from_provider_row(self, client, monkeypatch, tmp_test_dir):
        captured = {}

        def handler(request):
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"data": [{"id": "m1"}]})

        _patch_httpx(monkeypatch, handler)

        from pathlib import Path

        import aiosqlite

        db_path = Path(tmp_test_dir) / "test.db"
        async with aiosqlite.connect(db_path) as db:
            await db.execute("INSERT INTO secrets (name, value) VALUES (?, ?)", ("sk_store", "resolved-key"))
            await db.commit()

        provider_id = await _make_provider(client, api_key="SECRET:sk_store")
        resp = await client.post(
            "/api/providers/fetch_models",
            json={"type": "openai_compat", "provider_id": provider_id},
        )
        assert resp.status_code == 200
        assert captured["auth"] == "Bearer resolved-key"

    async def test_failure_returns_500(self, client, monkeypatch):
        _patch_httpx(monkeypatch, lambda r: httpx.Response(200, json={"data": []}))
        resp = await client.post(
            "/api/providers/fetch_models",
            json={"type": "unknown_type", "base_url": "http://example.com"},
        )
        assert resp.status_code == 500


class TestOpenRouterEndpoints:
    async def test_endpoints(self, client, monkeypatch):
        def handler(request):
            return httpx.Response(200, json={"data": {"endpoints": [{"id": 1}, {"id": 2}]}})

        _patch_httpx(monkeypatch, handler)
        resp = await client.get("/api/providers/openrouter/endpoints/some/model")
        assert resp.status_code == 200
        assert resp.json() == {"data": {"endpoints": [{"id": 1}, {"id": 2}]}}

    async def test_404_returns_empty(self, client, monkeypatch):
        _patch_httpx(monkeypatch, lambda r: httpx.Response(404))
        resp = await client.get("/api/providers/openrouter/endpoints/x")
        assert resp.json() == {"data": {"endpoints": []}}

    async def test_error_500(self, client, monkeypatch):
        _patch_httpx(monkeypatch, lambda r: httpx.Response(500))
        resp = await client.get("/api/providers/openrouter/endpoints/x")
        assert resp.status_code == 500


class TestSecrets:
    async def test_roundtrip_preview_and_delete(self, client, tmp_test_dir):
        resp = await client.post("/api/providers/secrets", json={"name": "long_key", "value": "abcdefghijklmnopqrstuvwxyz"})
        assert resp.json() == {"ok": True}
        resp = await client.post("/api/providers/secrets", json={"name": "short", "value": "tiny"})
        assert resp.status_code == 200

        data = (await client.get("/api/providers/secrets")).json()["data"]
        by_name = {s["name"]: s["preview"] for s in data}
        assert by_name["long_key"] == "abcd...wxyz"
        assert by_name["short"] == "***"

        assert (await client.delete("/api/providers/secrets/long_key")).status_code == 204
        data = (await client.get("/api/providers/secrets")).json()["data"]
        assert [s["name"] for s in data] == ["short"]


class TestProviderDetail:
    async def test_get_with_empty_api_key(self, client):
        pid = await _make_provider(client)
        data = (await client.get(f"/api/providers/{pid}")).json()
        assert data["api_key"] == ""

    async def test_update_params_and_empty_api_key(self, client, tmp_test_dir):
        db_path = Path(tmp_test_dir) / "test.db"
        pid = await _make_provider(client, api_key="sk-old")
        resp = await client.patch(f"/api/providers/{pid}", json={"params": {"top_p": 0.5}, "name": "Renamed"})
        assert resp.json() == {"ok": True}

        data = (await client.get(f"/api/providers/{pid}")).json()
        assert data["name"] == "Renamed"
        assert json.loads(data["params_json"]) == {"top_p": 0.5}

        await client.patch(f"/api/providers/{pid}", json={"api_key": ""})
        resp = await client.get(f"/api/providers/{pid}")
        assert resp.json()["api_key"] == "__HIDDEN__", "empty api_key update must be a no-op"
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute("SELECT api_key FROM providers WHERE id = ?", (pid,))
            assert (await cur.fetchone())[0] == "sk-old"

        assert (await client.patch(f"/api/providers/{pid}", json={})).json() == {"ok": True}


class TestBalance:
    async def test_openrouter_balance_and_cache(self, client, monkeypatch):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json={"data": {"total_credits": 100, "total_usage": 30}})

        _patch_httpx(monkeypatch, handler)
        pid = await _make_provider(client, ptype="openrouter", api_key="sk-bal")

        resp = await client.get(f"/api/providers/{pid}/balance")
        assert resp.json() == {"balances": [{"amount": 70, "currency": "USD"}]}
        await client.get(f"/api/providers/{pid}/balance")
        assert calls["n"] == 1, "balance must be cached for 60s"

    async def test_openrouter_401_empty_balances(self, client, monkeypatch):
        _patch_httpx(monkeypatch, lambda r: httpx.Response(401))
        pid = await _make_provider(client, ptype="openrouter", api_key="k")
        resp = await client.get(f"/api/providers/{pid}/balance")
        assert resp.json() == {"balances": []}

    async def test_deepseek_balance_infos(self, client, monkeypatch):
        def handler(request):
            return httpx.Response(200, json={"balance_infos": [
                {"total_balance": "12.5", "currency": "CNY"},
                {"total_balance": "3.0", "currency": "CNY"},
            ]})

        _patch_httpx(monkeypatch, handler)
        pid = await _make_provider(client, ptype="deepseek", api_key="k")
        resp = await client.get(f"/api/providers/{pid}/balance")
        assert resp.json() == {"balances": [
            {"amount": 12.5, "currency": "CNY"},
            {"amount": 3.0, "currency": "CNY"},
        ]}

    async def test_unsupported_type_400(self, client):
        pid = await _make_provider(client)
        assert (await client.get(f"/api/providers/{pid}/balance")).status_code == 400

    async def test_provider_not_found(self, client):
        assert (await client.get("/api/providers/nope/balance")).status_code == 404


class TestModelModalities:
    async def test_modalities_lookup_and_cache(self, client, monkeypatch):
        calls = {"n": 0}

        def handler(request):
            calls["n"] += 1
            return httpx.Response(200, json={"data": [
                {"id": "other/model", "architecture": {"input_modalities": ["text"]}},
                {"id": "my/model", "architecture": {"input_modalities": ["text", "image"]}},
            ]})

        _patch_httpx(monkeypatch, handler)

        from focus.routers.providers import get_openrouter_model_modalities

        assert await get_openrouter_model_modalities("my/model") == ["text", "image"]
        assert await get_openrouter_model_modalities("my/model") == ["text", "image"]
        assert calls["n"] == 1

    async def test_unknown_model_returns_none(self, client, monkeypatch):
        _patch_httpx(monkeypatch, lambda r: httpx.Response(200, json={"data": []}))

        from focus.routers.providers import get_openrouter_model_modalities

        assert await get_openrouter_model_modalities("nope") is None
