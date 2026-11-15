from focus.core.prefs import DEFAULTS, normalize


async def test_prefs_default_on_a_fresh_database(client):
    resp = await client.get("/api/settings/prefs")
    assert resp.status_code == 200
    assert resp.json() == DEFAULTS


async def test_partial_update_merges(client):
    resp = await client.put("/api/settings/prefs", json={"send_key": "ctrl_enter"})
    assert resp.status_code == 200

    resp = await client.put("/api/settings/prefs", json={"clock": "12h"})
    assert resp.json()["send_key"] == "ctrl_enter"
    assert resp.json()["clock"] == "12h"
    assert resp.json()["chat_width"] == DEFAULTS["chat_width"]

    resp = await client.get("/api/settings/prefs")
    assert resp.json()["send_key"] == "ctrl_enter"


async def test_invalid_values_fall_back_to_the_default(client):
    resp = await client.put(
        "/api/settings/prefs",
        json={"send_key": "space", "clock": "sun", "prune_messages": "no"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["send_key"] == DEFAULTS["send_key"]
    assert body["clock"] == DEFAULTS["clock"]
    assert body["prune_messages"] == DEFAULTS["prune_messages"]


async def test_width_is_clamped(client):
    resp = await client.put("/api/settings/prefs", json={"chat_width": 40})
    assert resp.json()["chat_width"] == 480

    resp = await client.put("/api/settings/prefs", json={"chat_width": 99999})
    assert resp.json()["chat_width"] == 1600


def test_normalize_keeps_known_keys_only():
    prefs = normalize({"send_key": "ctrl_enter", "unknown": 1, "chat_width": True})

    assert prefs == {**DEFAULTS, "send_key": "ctrl_enter"}


def test_normalize_survives_garbage():
    assert normalize("nope") == DEFAULTS
    assert normalize(None) == DEFAULTS
