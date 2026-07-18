async def create_character(client, name="Test Char", **overrides):
    body = {
        "name": name,
        "description": "Desc",
        "personality": "Neutral",
        "scenario": "Test",
        **overrides,
    }
    resp = await client.post("/api/characters/", json=body)
    assert resp.status_code == 201
    return resp.json()


async def create_persona(client, name="Test Persona", **overrides):
    body = {"name": name, "description": "A persona", **overrides}
    resp = await client.post("/api/personas/", json=body)
    assert resp.status_code == 201
    return resp.json()


async def create_preset(client, name="Test Preset"):
    resp = await client.post("/api/presets/", data={"name": name})
    assert resp.status_code == 201
    return resp.json()


async def create_chat(client, character_id=None, persona_id=None, preset_id=None, title="Test Chat"):
    body = {"title": title}
    if character_id:
        body["character_id"] = character_id
    if persona_id:
        body["persona_id"] = persona_id
    if preset_id:
        body["preset_id"] = preset_id
    resp = await client.post("/api/chats/", json=body)
    assert resp.status_code == 201
    return resp.json()
