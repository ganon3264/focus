"""Tests for the page/partial routes (focus/routers/pages.py).

These exercise the full HTML rendering path: the chat page with real
messages, the chat redirects, and the HTMX partial endpoints. They also
cover the crud helpers only reachable through pages (get_chat_messages,
get_chats_sidebar, get_counts, get_preset).
"""

from tests.helpers import create_character, create_chat, create_persona, create_preset


async def _seed_chat(client):
    char = await create_character(client, "PageChar", first_mes="Greetings {{char}}")
    persona = await create_persona(client, "PagePersona")
    preset = await create_preset(client, "PagePreset")
    chat = await create_chat(client, char["id"], persona["id"], preset["id"], title="Page Chat")
    return chat, char, persona, preset


class TestChatRedirect:
    async def test_redirects_to_latest_chat(self, client):
        chat, _, _, _ = await _seed_chat(client)
        resp = await client.get("/chat", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == f"/chat/{chat['id']}"

    async def test_redirects_to_character_chat(self, client):
        char = await create_character(client, "Target")
        chat1 = await create_chat(client, character_id=char["id"], title="One")
        await create_chat(client, title="Other")
        resp = await client.get(f"/chat?character_id={char['id']}", follow_redirects=False)
        assert resp.headers["location"] == f"/chat/{chat1['id']}"

    async def test_greeter_state_without_chats(self, client):
        resp = await client.get("/chat")
        assert resp.status_code == 200
        assert "chat.html" in resp.text or "Focus" in resp.text

    async def test_greeter_state_with_character_filter(self, client):
        char = await create_character(client, "Lonely")
        resp = await client.get(f"/chat?character_id={char['id']}")
        assert resp.status_code == 200


class TestChatPage:
    async def test_full_chat_page_renders(self, client, tmp_test_dir):
        chat, char, persona, preset = await _seed_chat(client)

        # Seed a conversation via the stream endpoint? No — use the API edit
        # path is unavailable for new messages, so insert via a fake stream is
        # overkill; the greeting messages already exist from create_chat.
        resp = await client.get(f"/chat/{chat['id']}")
        assert resp.status_code == 200
        assert f"/chat/{chat['id']}" in resp.text
        assert "PageChar" in resp.text

        # Chat page must render with the greeting message present
        assert "Greetings" in resp.text

    async def test_unknown_chat_redirects(self, client):
        resp = await client.get("/chat/does-not-exist", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == "/chat"

    async def test_message_list_partial(self, client):
        chat, _, _, _ = await _seed_chat(client)
        resp = await client.get(f"/partials/message-list/{chat['id']}")
        assert resp.status_code == 200
        assert "Greetings" in resp.text

    async def test_single_message_partial(self, client, tmp_test_dir):
        chat, _, _, _ = await _seed_chat(client)
        detail = await client.get(f"/api/chats/{chat['id']}")
        greeting = detail.json()["messages"][0]

        resp = await client.get(
            f"/partials/message/{chat['id']}/{greeting['id']}?msg_index=0&is_latest=true"
        )
        assert resp.status_code == 200
        assert "Greetings" in resp.text

        resp = await client.get(f"/partials/message/{chat['id']}/nope")
        assert resp.status_code == 404

    async def test_chat_list_partial(self, client):
        chat, _, _, _ = await _seed_chat(client)
        resp = await client.get(f"/partials/chat-list?current_chat_id={chat['id']}")
        assert resp.status_code == 200
        assert chat["id"] in resp.text

    async def test_chat_list_partial_filtered_by_character(self, client):
        char = await create_character(client, "FilterChar")
        chat = await create_chat(client, character_id=char["id"], title="F")
        resp = await client.get(f"/partials/chat-list?character_id={char['id']}")
        assert resp.status_code == 200
        assert chat["id"] in resp.text


class TestStandalonePages:
    async def test_characters_page(self, client):
        await create_character(client, "Standalone")
        resp = await client.get("/characters")
        assert resp.status_code == 200
        assert "Standalone" in resp.text

    async def test_providers_page(self, client):
        resp = await client.get("/providers")
        assert resp.status_code == 200

    async def test_personas_page(self, client):
        await create_persona(client, "StandalonePersona")
        resp = await client.get("/personas")
        assert resp.status_code == 200
        assert "StandalonePersona" in resp.text


class TestPresetPartials:
    async def test_preset_selector(self, client):
        chat, _, _, preset = await _seed_chat(client)
        resp = await client.get(f"/partials/preset-selector?chat_id={chat['id']}")
        assert resp.status_code == 200
        assert preset["id"] in resp.text

    async def test_selection_state_oob_fragments(self, client):
        chat, char, persona, preset = await _seed_chat(client)
        resp = await client.get(
            f"/partials/selection-state?chat_id={chat['id']}"
            f"&preset_id={preset['id']}&character_id={char['id']}&persona_id={persona['id']}"
        )
        assert resp.status_code == 200
        # every selection-dependent pane is an out-of-band swap
        for target in ("preset-selector", "preset-variables", "arranger-modal-body", "chat-list"):
            assert f'id="{target}" hx-swap-oob="innerHTML"' in resp.text, target
        assert preset["id"] in resp.text
        assert chat["id"] in resp.text

    async def test_selection_state_greeter_no_params(self, client):
        # No chat / no selection — the greeter state. Must not 500 and must
        # render the empty-state panes.
        resp = await client.get("/partials/selection-state")
        assert resp.status_code == 200
        assert 'id="preset-selector" hx-swap-oob="innerHTML"' in resp.text
        assert "Select a preset to edit variables." in resp.text
        assert "Select a preset first." in resp.text

    async def test_selection_state_reflects_persona_after_patch(self, client):
        chat, char, _, preset = await _seed_chat(client)
        persona_b = await create_persona(client, "PersonaB")
        resp = await client.patch(f"/api/chats/{chat['id']}", json={"persona_id": persona_b["id"]})
        assert resp.status_code == 200

        resp = await client.get(
            f"/partials/selection-state?chat_id={chat['id']}"
            f"&preset_id={preset['id']}&character_id={char['id']}&persona_id={persona_b['id']}"
        )
        assert resp.status_code == 200
        assert "PersonaB" in resp.text
        assert "PagePersona" not in resp.text

    async def test_preset_variables_and_group(self, client):
        _, _, _, preset = await _seed_chat(client)
        resp = await client.get(f"/partials/preset-variables/{preset['id']}")
        assert resp.status_code == 200
        resp = await client.get(f"/partials/preset-variables/{preset['id']}/group/None")
        assert resp.status_code == 200

    async def test_preset_editor_and_arranger(self, client):
        _, _, _, preset = await _seed_chat(client)
        for path in (
            f"/partials/preset-editor/{preset['id']}",
            f"/partials/prompt-arranger/{preset['id']}",
        ):
            resp = await client.get(path)
            assert resp.status_code == 200, path

        blocks = (await client.get(f"/api/presets/{preset['id']}")).json()["blocks"]
        resp = await client.get(f"/partials/prompt-arranger/{preset['id']}/block/{blocks[0]['id']}")
        assert resp.status_code == 200
        resp = await client.get(f"/partials/prompt-arranger/{preset['id']}/block/nope")
        assert resp.status_code == 404


class TestModalPartials:
    async def test_providers_modal_with_secrets(self, client, tmp_test_dir):
        from pathlib import Path

        import aiosqlite

        db_path = Path(tmp_test_dir) / "test.db"
        async with aiosqlite.connect(db_path) as db:
            await db.execute("INSERT INTO secrets (name, value) VALUES (?, ?)", ("sk_global", "v"))
            await db.commit()

        resp = await client.get("/partials/providers-modal")
        assert resp.status_code == 200
        assert "modal-secrets" in resp.text

    async def test_presets_modal(self, client):
        preset = await create_preset(client, "ModalPreset")
        resp = await client.get("/partials/presets-modal")
        assert resp.status_code == 200
        assert preset["id"] in resp.text

    async def test_export_entities(self, client):
        char = await create_character(client, "ExportMe")
        await create_character(client, "KeepOut")
        await create_persona(client, "ExportPersona")
        preset = await create_preset(client, "ExportPreset")

        resp = await client.get("/partials/export-entities?type=characters&filter=export")
        assert resp.status_code == 200
        assert char["id"] in resp.text
        assert "KeepOut" not in resp.text

        resp = await client.get("/partials/export-entities?type=personas&filter=")
        assert "ExportPersona" in resp.text

        resp = await client.get("/partials/export-entities?type=presets&filter=")
        assert preset["id"] in resp.text

        resp = await client.get("/partials/export-entities?type=bogus&filter=")
        assert resp.status_code == 200

    async def test_persona_card_partial(self, client):
        p = await create_persona(client, "Carded")
        resp = await client.get(f"/partials/persona-card/{p['id']}")
        assert resp.status_code == 200
        assert (await client.get("/partials/persona-card/nope")).status_code == 404

    async def test_character_card_partial(self, client):
        char = await create_character(client, "CardedChar")
        resp = await client.get(f"/partials/character-card/{char['id']}")
        assert resp.status_code == 200
        assert (await client.get("/partials/character-card/nope")).status_code == 404

    async def test_persona_modal_card_partial(self, client):
        p = await create_persona(client, "ModalCarded")
        resp = await client.get(f"/partials/persona-modal-card/{p['id']}")
        assert resp.status_code == 200
        assert (await client.get("/partials/persona-modal-card/nope")).status_code == 404
