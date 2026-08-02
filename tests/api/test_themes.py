import pytest

from tests.helpers import create_character

COLORS = {
    "--bg": "#0b0d10",
    "--surface": "#13151a",
    "--accent": "#6366f1",
    "--text": "#f1f3f5",
}


async def _create_custom(client, name="My Theme"):
    resp = await client.post("/api/themes/", json={"name": name, "colors": COLORS})
    assert resp.status_code == 201
    return resp.json()["id"]


async def test_list_seeded_builtins(client):
    resp = await client.get("/api/themes/")
    assert resp.status_code == 200
    themes = resp.json()
    assert len(themes) == 3
    assert all(t["is_system"] for t in themes)
    slate = next(t for t in themes if t["id"] == "builtin-slate")
    assert slate["colors"]["--bg"] == "#0b0d10"
    assert "created_at" in slate


async def test_create_theme(client):
    theme_id = await _create_custom(client)
    resp = await client.get("/api/themes/")
    theme = next(t for t in resp.json() if t["id"] == theme_id)
    assert theme["is_system"] is False
    assert theme["colors"] == COLORS


async def test_create_theme_requires_name(client):
    resp = await client.post("/api/themes/", json={"name": "   ", "colors": COLORS})
    assert resp.status_code == 422


async def test_update_custom_theme(client):
    theme_id = await _create_custom(client)
    resp = await client.patch(
        f"/api/themes/{theme_id}",
        json={"name": "Renamed", "colors": dict(COLORS, **{"--accent": "#123456"})},
    )
    assert resp.status_code == 200
    resp = await client.get("/api/themes/")
    theme = next(t for t in resp.json() if t["id"] == theme_id)
    assert theme["name"] == "Renamed"
    assert theme["colors"]["--accent"] == "#123456"


async def test_update_builtin_theme_in_place(client):
    resp = await client.patch(
        "/api/themes/builtin-slate",
        json={"name": "My Slate", "colors": dict(COLORS, **{"--bg": "#101010"})},
    )
    assert resp.status_code == 200
    resp = await client.get("/api/themes/")
    theme = next(t for t in resp.json() if t["id"] == "builtin-slate")
    assert theme["name"] == "My Slate"
    assert theme["colors"]["--bg"] == "#101010"


async def test_update_missing_theme(client):
    resp = await client.patch("/api/themes/theme-nope", json={"name": "X"})
    assert resp.status_code == 404


async def test_reset_builtin_theme(client):
    await client.patch(
        "/api/themes/builtin-slate",
        json={"name": "Ruined", "colors": {"--bg": "#ff0000"}},
    )
    resp = await client.post("/api/themes/builtin-slate/reset")
    assert resp.status_code == 200
    themes = (await client.get("/api/themes/")).json()
    slate = next(t for t in themes if t["id"] == "builtin-slate")
    assert slate["name"] == "Slate (Default)"
    assert slate["colors"]["--bg"] == "#0b0d10"


async def test_reset_custom_theme_conflict(client):
    theme_id = await _create_custom(client)
    resp = await client.post(f"/api/themes/{theme_id}/reset")
    assert resp.status_code == 409


async def test_reset_missing_theme(client):
    resp = await client.post("/api/themes/theme-nope/reset")
    assert resp.status_code == 404


async def test_delete_custom_theme(client):
    theme_id = await _create_custom(client)
    resp = await client.delete(f"/api/themes/{theme_id}")
    assert resp.status_code == 204
    resp = await client.get("/api/themes/")
    assert all(t["id"] != theme_id for t in resp.json())


async def test_delete_system_theme_conflict(client):
    resp = await client.delete("/api/themes/builtin-slate")
    assert resp.status_code == 409


async def test_delete_dark_slot_theme_falls_back(client):
    theme_id = await _create_custom(client)
    await client.put("/api/settings/theme", json={"slot": "dark", "theme_id": theme_id})
    await client.delete(f"/api/themes/{theme_id}")
    settings = (await client.get("/api/settings/")).json()
    assert settings["dark_theme_id"] == "builtin-slate"


async def test_delete_light_slot_theme_falls_back(client):
    theme_id = await _create_custom(client)
    await client.put("/api/settings/theme", json={"slot": "light", "theme_id": theme_id})
    await client.delete(f"/api/themes/{theme_id}")
    settings = (await client.get("/api/settings/")).json()
    assert settings["light_theme_id"] == "builtin-light"


async def test_apply_theme_slot_dark(client):
    resp = await client.put(
        "/api/settings/theme",
        json={"slot": "dark", "theme_id": "builtin-midnight"},
    )
    assert resp.status_code == 200
    settings = (await client.get("/api/settings/")).json()
    assert settings["dark_theme_id"] == "builtin-midnight"


async def test_apply_theme_slot_light(client):
    resp = await client.put(
        "/api/settings/theme",
        json={"slot": "light", "theme_id": "builtin-slate"},
    )
    assert resp.status_code == 200
    settings = (await client.get("/api/settings/")).json()
    assert settings["light_theme_id"] == "builtin-slate"


async def test_apply_theme_missing(client):
    resp = await client.put(
        "/api/settings/theme",
        json={"slot": "dark", "theme_id": "theme-nope"},
    )
    assert resp.status_code == 404


async def test_apply_theme_invalid_slot(client):
    resp = await client.put(
        "/api/settings/theme",
        json={"slot": "banana", "theme_id": "builtin-slate"},
    )
    assert resp.status_code == 422


async def test_character_theme_roundtrip(client):
    char = await create_character(client, "Themed")
    resp = await client.patch(
        f"/api/characters/{char['id']}",
        json={"theme_id": "builtin-midnight"},
    )
    assert resp.status_code == 200
    resp = await client.get(f"/api/characters/{char['id']}")
    assert resp.json()["theme_id"] == "builtin-midnight"


async def test_character_theme_cleared(client):
    char = await create_character(client, "Themed")
    await client.patch(f"/api/characters/{char['id']}", json={"theme_id": "builtin-midnight"})
    resp = await client.patch(f"/api/characters/{char['id']}", json={"theme_id": ""})
    assert resp.status_code == 200
    resp = await client.get(f"/api/characters/{char['id']}")
    assert resp.json()["theme_id"] is None


async def test_character_theme_invalid_reference_rejected(client):
    char = await create_character(client, "Themed")
    resp = await client.patch(f"/api/characters/{char['id']}", json={"theme_id": "theme-nope"})
    assert resp.status_code == 400


@pytest.mark.parametrize(
    "target",
    ["/chat?character_id=does-not-exist", "/chat"],
)
async def test_chat_pages_embed_theme_state(client, target):
    resp = await client.get(target, follow_redirects=False)
    assert resp.status_code in (200, 307)
    if resp.status_code == 200:
        html = resp.text
        assert "window.THEMES" in html
        assert "window.THEME_STATE" in html
        assert '"builtin-slate"' in html
        assert '"builtin-light"' in html
