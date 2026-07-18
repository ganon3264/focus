"""Tests for state management: StateManager JS module + server-side contract.

Node must be installed. The JS tests are in tests/test_state_manager.js.
"""

import os
import subprocess

from tests.conftest import create_character, create_chat, create_persona, create_preset

def test_state_manager_js():
    """Run the Node-based unit tests for StateManager."""
    test_file = os.path.join(os.path.dirname(__file__), "test_state_manager.js")
    result = subprocess.run(["node", test_file], capture_output=True, text=True)
    assert result.returncode == 0, (
        f"StateManager JS tests failed:\n{result.stdout}\n{result.stderr}"
    )

class TestPresetLifecycle:
    """Tests that the server behaves correctly for operations the StateManager depends on."""

    async def test_set_preset_on_chat(self, client):
        """PATCH /api/chats/{id} with preset_id, then verify it's stored."""
        ch = await create_chat(client)
        pr = await create_preset(client, "TestPreset")

        resp = await client.patch(f"/api/chats/{ch['id']}", json={"preset_id": pr["id"]})
        assert resp.status_code == 200

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["preset_id"] == pr["id"]

    async def test_clear_preset_on_chat(self, client):
        """PATCH preset_id to null clears it."""
        pr = await create_preset(client, "TestPreset")
        ch = await create_chat(client, preset_id=pr["id"])

        resp = await client.patch(f"/api/chats/{ch['id']}", json={"preset_id": None})
        assert resp.status_code == 200

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["preset_id"] is None

    async def test_delete_preset_clears_chat_preset_id(self, client):
        """Deleting a preset should cascade — chat's preset_id should be None."""
        pr = await create_preset(client, "TestPreset")
        ch = await create_chat(client, preset_id=pr["id"])

        await client.delete(f"/api/presets/{pr['id']}")

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["preset_id"] is None

    async def test_delete_preset_cascades_blocks(self, client):
        """Deleting a preset deletes its blocks from the DB."""
        pr = await create_preset(client, "TestPreset")
        presets = await client.get(f"/api/presets/{pr['id']}")
        assert len(presets.json()["blocks"]) >= 1  # default block exists

        await client.delete(f"/api/presets/{pr['id']}")

        resp = await client.get(f"/api/presets/{pr['id']}")
        assert resp.status_code == 404

class TestCharacterLifecycle:
    async def test_set_character_on_chat(self, client):
        """PATCH /api/chats/{id} with character_id persists."""
        ch = await create_chat(client)
        c = await create_character(client, "Alice")

        resp = await client.patch(f"/api/chats/{ch['id']}", json={"character_id": c["id"]})
        assert resp.status_code == 200

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["character_id"] == c["id"]

    async def test_hard_delete_character_orphans_chat(self, client):
        """Hard-deleting a character sets chat.character_id to None."""
        c = await create_character(client, "Bob")
        ch = await create_chat(client, character_id=c["id"])

        await client.delete(f"/api/characters/{c['id']}?hard=true")

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["character_id"] is None

class TestPersonaLifecycle:
    async def test_set_persona_on_chat(self, client):
        """PATCH /api/chats/{id} with persona_id persists."""
        ch = await create_chat(client)
        p = await create_persona(client, "MyPersona")

        resp = await client.patch(f"/api/chats/{ch['id']}", json={"persona_id": p["id"]})
        assert resp.status_code == 200

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["persona_id"] == p["id"]

class TestModalPartials:
    """Tests that partial templates render correctly with query params — the
    server-side half of the character/persona highlight logic."""

    async def test_characters_modal_highlights_current(self, client):
        """GET /partials/characters-modal?current_character_id=X renders active class on card X."""
        c1 = await create_character(client, "Alice")
        c2 = await create_character(client, "Bob")

        resp = await client.get(f"/partials/characters-modal?current_character_id={c1['id']}")
        assert resp.status_code == 200
        html = resp.text

        # Alice's card should have the "active" class
        assert 'class="card active"' in html
        assert f'id="char-card-{c1["id"]}"' in html
        assert f'id="char-card-{c2["id"]}"' in html

    async def test_characters_modal_no_current_no_highlight(self, client):
        """Without current_character_id, no card gets the active class."""
        await create_character(client, "Alice")
        resp = await client.get("/partials/characters-modal")
        assert resp.status_code == 200
        assert 'class="card active"' not in resp.text

    async def test_personas_modal_highlights_current(self, client):
        """GET /partials/personas-modal?current_persona_id=X renders active class on card X."""
        p1 = await create_persona(client, "PersonaOne")
        p2 = await create_persona(client, "PersonaTwo")

        resp = await client.get(f"/partials/personas-modal?current_persona_id={p1['id']}")
        assert resp.status_code == 200
        html = resp.text

        assert 'class="card active"' in html
        assert f'id="persona-card-{p1["id"]}"' in html
        assert f'id="persona-card-{p2["id"]}"' in html
