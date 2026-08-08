"""Regression tests: API collection routes must never redirect.

The frontend calls API endpoints without a trailing slash (e.g. POST
/api/providers). With FastAPI's default redirect_slashes, those used to
answer with a 307 to an absolute URL built from the request scope, which
breaks behind reverse proxies (mixed-content block / NS_ERROR_UNEXPECTED).
Both slash variants of every collection route must answer directly.
"""

import pytest


@pytest.mark.parametrize(
    "path,method,payload",
    [
        ("/api/providers", "POST", {"name": "P", "type": "openai_compat", "model": "m"}),
        ("/api/providers/", "POST", {"name": "P", "type": "openai_compat", "model": "m"}),
        ("/api/chats", "POST", {"title": "Chat"}),
        ("/api/chats/", "POST", {"title": "Chat"}),
        ("/api/characters", "POST", {"name": "Char"}),
        ("/api/personas", "POST", {"name": "Persona"}),
        ("/api/presets", "POST", {"name": "Preset"}),
    ],
)
async def test_collection_posts_do_not_redirect(client, path, method, payload):
    if path.startswith("/api/presets"):
        resp = await client.request(method, path, data=payload, follow_redirects=False)
    else:
        resp = await client.request(method, path, json=payload, follow_redirects=False)
    assert resp.status_code == 201, (path, resp.status_code, resp.headers.get("location"))
    assert resp.status_code not in range(300, 400)


@pytest.mark.parametrize(
    "path,method,payload",
    [
        ("/api/providers", "GET", None),
        ("/api/providers/", "GET", None),
        ("/api/chats", "GET", None),
        ("/api/chats/", "GET", None),
        ("/api/characters", "GET", None),
        ("/api/characters/", "GET", None),
        ("/api/personas", "GET", None),
        ("/api/personas/", "GET", None),
        ("/api/presets", "GET", None),
        ("/api/presets/", "GET", None),
        ("/api/settings", "GET", None),
        ("/api/settings/", "GET", None),
        ("/api/backups", "GET", None),
        ("/api/backups/", "GET", None),
        ("/api/themes", "GET", None),
        ("/api/themes/", "GET", None),
        ("/api/settings", "PATCH", {"key": "k", "value": "v"}),
        ("/api/settings/", "PATCH", {"key": "k", "value": "v"}),
    ],
)
async def test_collection_reads_do_not_redirect(client, path, method, payload):
    kwargs = {"follow_redirects": False}
    if payload is not None:
        kwargs["json"] = payload
    resp = await client.request(method, path, **kwargs)
    assert resp.status_code == 200, (path, resp.status_code, resp.headers.get("location"))
    assert resp.status_code not in range(300, 400)


async def test_page_routes_still_serve(client):
    resp = await client.get("/chat", follow_redirects=False)
    assert resp.status_code == 200
    assert "window.THEMES" in resp.text


async def test_proxy_scenario_no_redirect(client):
    """Reported setup: HTTPS at the proxy edge, plain HTTP backend, forwarded headers."""
    headers = {"X-Forwarded-Proto": "https", "Origin": "http://test"}
    for path, payload in [
        ("/api/providers", {"name": "P", "type": "openai_compat", "model": "m"}),
        ("/api/chats", {"title": "Chat"}),
    ]:
        resp = await client.post(path, json=payload, headers=headers, follow_redirects=False)
        assert resp.status_code == 201, (path, resp.status_code, resp.headers.get("location"))
        assert resp.status_code not in range(300, 400)


def test_relativize_location():
    from main import _relativize_location

    assert _relativize_location("http://test/api/x", "test") == "/api/x"
    assert _relativize_location("http://test:8000/api/x", "test:8000") == "/api/x"
    assert _relativize_location("http://test", "test") == "/"
    assert _relativize_location("/chat", "test") == "/chat"
    assert _relativize_location("http://other.example/x", "test") == "http://other.example/x"
    assert _relativize_location("http://test/x", "test:8000") == "http://test/x"
