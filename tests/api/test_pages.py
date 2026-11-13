"""Tests for the page/partial routes (focus/routers/pages.py).

These exercise the full HTML rendering path: the chat page with real
messages, the chat redirects, and the HTMX partial endpoints. They also
cover the crud helpers only reachable through pages (get_chat_messages,
get_chats_sidebar, get_counts, get_preset).
"""

import os
import re
import uuid
from datetime import UTC, datetime

import aiosqlite

from tests.helpers import create_character, create_chat, create_persona, create_preset


async def _seed_message(db_path: str, chat_id: str, role: str, position: int, content: str) -> str:
    msg_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, active_index, created_at)"
            " VALUES (?, ?, ?, ?, 0, ?)",
            (msg_id, chat_id, role, position, now),
        )
        await db.execute(
            "INSERT INTO message_variants"
            " (id, message_id, variant_index, content, created_at, model_name)"
            " VALUES (?, ?, 0, ?, ?, 'fake-model')",
            (str(uuid.uuid4()), msg_id, content, now),
        )
        await db.commit()
    return msg_id


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

    async def test_greeter_inherits_the_last_used_preset(self, client):
        older = await create_preset(client, "Older")
        newer = await create_preset(client, "Newer")
        await create_chat(client, preset_id=older["id"], title="Writes with Older")
        lonely = await create_character(client, "Lonely")

        resp = await client.get(f"/chat?character_id={lonely['id']}")

        assert f"preset_id: '{older['id']}'" in resp.text
        assert f"preset_id: '{newer['id']}'" not in resp.text

    async def test_greeter_falls_back_to_the_newest_preset_without_history(self, client):
        await create_preset(client, "Older")
        newest = await create_preset(client, "Newest")

        resp = await client.get("/chat")

        assert f"preset_id: '{newest['id']}'" in resp.text


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

    async def test_advanced_modal_has_stale_chat_purge(self, client):
        chat, _, _, _ = await _seed_chat(client)
        resp = await client.get(f"/chat/{chat['id']}")
        assert 'id="purge-days"' in resp.text
        assert 'id="btn-purge-old-chats"' in resp.text
        assert "Older than 1 year" in resp.text

    async def test_unknown_chat_redirects(self, client):
        resp = await client.get("/chat/does-not-exist", follow_redirects=False)
        assert resp.status_code in (302, 307)
        assert resp.headers["location"] == "/chat"

    async def test_chat_html_is_gzipped(self, client):
        chat, _, _, _ = await _seed_chat(client)
        resp = await client.get(
            f"/chat/{chat['id']}", headers={"Accept-Encoding": "gzip"}
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-encoding") == "gzip"

    async def test_binary_and_sse_content_types_excluded_from_gzip(self):
        import starlette.middleware.gzip as gz

        import main  # noqa: F401  (applies the middleware's exclusion config)

        excluded = gz.DEFAULT_EXCLUDED_CONTENT_TYPES
        # SSE must stay raw so tokens stream; binaries are already compressed.
        for content_type in ("text/event-stream", "image/png", "image/webp", "font/"):
            assert content_type in excluded

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


class TestChatPagination:
    def test_page_window_centres_on_current(self):
        from focus.crud import _page_window

        assert _page_window(1, 6) == [1, 2, 3, 4, 5]
        assert _page_window(3, 6) == [1, 2, 3, 4, 5]
        assert _page_window(4, 6) == [2, 3, 4, 5, 6]
        assert _page_window(6, 6) == [2, 3, 4, 5, 6]
        assert _page_window(2, 3) == [1, 2, 3]

    async def _seed(self, client, count, character_id):
        return [await create_chat(client, character_id=character_id, title=f"Chat {i}") for i in range(count)]

    async def test_pager_renders_for_multiple_pages(self, client):
        char = await create_character(client, "Paged")
        await self._seed(client, 17, char["id"])
        resp = await client.get(f"/partials/chat-list?character_id={char['id']}")
        assert resp.status_code == 200
        assert 'class="pager"' in resp.text
        assert 'data-chat-page="1"' in resp.text
        assert "goToChatPage(1)" in resp.text
        assert "goToChatPage(2)" in resp.text

    async def test_pager_hidden_for_single_page(self, client):
        char = await create_character(client, "Single")
        await create_chat(client, character_id=char["id"], title="Only")
        resp = await client.get(f"/partials/chat-list?character_id={char['id']}")
        assert resp.status_code == 200
        assert 'class="pager"' not in resp.text

    async def test_second_page_has_older_chats(self, client):
        char = await create_character(client, "Paged2")
        chats = await self._seed(client, 16, char["id"])
        page1 = await client.get(f"/partials/chat-list?character_id={char['id']}&page=1")
        page2 = await client.get(f"/partials/chat-list?character_id={char['id']}&page=2")
        assert page1.status_code == 200 and page2.status_code == 200
        assert chats[-1]["id"] in page1.text
        assert chats[0]["id"] not in page1.text
        assert chats[0]["id"] in page2.text
        assert chats[-1]["id"] not in page2.text

    async def test_out_of_range_page_is_clamped(self, client):
        char = await create_character(client, "Paged3")
        await self._seed(client, 16, char["id"])
        resp = await client.get(f"/partials/chat-list?character_id={char['id']}&page=99")
        assert resp.status_code == 200
        assert 'data-chat-page="2"' in resp.text

    async def test_chat_page_opens_page_containing_chat(self, client):
        char = await create_character(client, "Paged4")
        chats = await self._seed(client, 16, char["id"])
        oldest = chats[0]
        resp = await client.get(f"/chat/{oldest['id']}")
        assert resp.status_code == 200
        assert 'data-chat-page="2"' in resp.text
        assert 'class="row group active"' in resp.text

    async def test_preview_is_clipped_to_one_row(self, client):
        long_text = "word " * 200
        char = await create_character(client, "PreviewChar", first_mes=long_text)
        chat = await create_chat(client, char["id"], title="Preview Chat")
        resp = await client.get(f"/partials/chat-list?current_chat_id={chat['id']}")
        assert resp.status_code == 200
        assert long_text[:400] in resp.text
        assert long_text[:401] not in resp.text

    async def test_selection_state_preserves_page(self, client):
        char = await create_character(client, "Paged5")
        await self._seed(client, 16, char["id"])
        resp = await client.get(f"/partials/selection-state?character_id={char['id']}&page=2")
        assert resp.status_code == 200
        assert 'id="chat-list" hx-swap-oob="innerHTML"' in resp.text
        assert 'data-chat-page="2"' in resp.text


class TestListSortPrefs:
    """A list modal's sort mode is a settings row, rendered into the grid —
    the client keeps no second copy in browser storage."""

    async def test_defaults_when_nothing_is_stored(self, client):
        await create_character(client, "Sorter")
        resp = await client.get("/partials/characters-modal")
        assert resp.status_code == 200
        assert 'data-sort-mode="newest"' in resp.text

    async def test_stored_mode_is_rendered(self, client):
        await create_character(client, "Sorter")
        await client.patch("/api/settings/", json={"key": "focus_char_sort", "value": "az"})
        resp = await client.get("/partials/characters-modal")
        assert 'data-sort-mode="az"' in resp.text

    async def test_unknown_mode_falls_back_to_the_default(self, client):
        await create_character(client, "Sorter")
        await client.patch("/api/settings/", json={"key": "focus_char_sort", "value": "nonsense"})
        resp = await client.get("/partials/characters-modal")
        assert 'data-sort-mode="newest"' in resp.text

    async def test_tools_default_is_az(self, client):
        chat, _, _, _ = await _seed_chat(client)
        resp = await client.get(f"/chat/{chat['id']}")
        assert "sortMode: 'az'" in resp.text


class TestStandalonePagesGone:
    """Characters, personas and providers live only in their modals; the old
    standalone pages were removed and must not be reachable."""

    async def test_characters_page_removed(self, client):
        await create_character(client, "Standalone")
        resp = await client.get("/characters")
        assert resp.status_code == 404

    async def test_providers_page_removed(self, client):
        resp = await client.get("/providers")
        assert resp.status_code == 404

    async def test_personas_page_removed(self, client):
        await create_persona(client, "StandalonePersona")
        resp = await client.get("/personas")
        assert resp.status_code == 404


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
        for target in ("preset-selector", "preset-variables", "arranger-modal-body", "chat-list", "chat-pager"):
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

    async def test_prompt_arranger(self, client):
        _, _, _, preset = await _seed_chat(client)
        resp = await client.get(f"/partials/prompt-arranger/{preset['id']}")
        assert resp.status_code == 200

        blocks = (await client.get(f"/api/presets/{preset['id']}")).json()["blocks"]
        resp = await client.get(f"/partials/prompt-arranger/{preset['id']}/block/{blocks[0]['id']}")
        assert resp.status_code == 200
        resp = await client.get(f"/partials/prompt-arranger/{preset['id']}/block/nope")
        assert resp.status_code == 404


class TestModalPartials:
    async def test_secrets_partial_lists_keys_with_preview(self, client):
        await client.post(
            "/api/providers/secrets", json={"name": "sk_long", "value": "abcdefghijklmnopqrstuvwxyz"}
        )
        await client.post("/api/providers/secrets", json={"name": "sk_short", "value": "tiny"})

        resp = await client.get("/partials/secrets")
        assert resp.status_code == 200
        assert "2 saved keys" in resp.text
        assert "sk_long" in resp.text
        assert "abcd...wxyz" in resp.text
        # The value never reaches the page: only the masked preview does.
        assert "abcdefghijklmnopqrstuvwxyz" not in resp.text
        # Manage mode rows are readouts, not pick targets.
        assert 'data-action="actionUseSecret"' not in resp.text

    async def test_secrets_partial_pick_mode_makes_rows_selectable(self, client):
        await client.post("/api/providers/secrets", json={"name": "sk_pick", "value": "v"})

        resp = await client.get("/partials/secrets?pick=1")
        assert resp.status_code == 200
        assert 'data-action="actionUseSecret"' in resp.text
        assert 'data-name="sk_pick"' in resp.text

    async def test_secrets_partial_empty_library_has_no_rows(self, client):
        resp = await client.get("/partials/secrets")
        assert resp.status_code == 200
        assert "0 saved keys" in resp.text
        assert "No saved keys yet." in resp.text
        assert "secret-row" not in resp.text

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


class TestStaticCachePolicy:
    def test_cache_control_toggle(self):
        from main import RevalidatedStaticFiles

        assert (
            RevalidatedStaticFiles(directory="static", cache_assets=False)._cache_control
            == "public, no-cache"
        )
        assert (
            RevalidatedStaticFiles(directory="static", cache_assets=True)._cache_control
            == "public, max-age=31536000, immutable"
        )


class TestHealth:
    async def test_health_answers_without_touching_the_db(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


class TestMessageListPartial:
    """`?ids=` narrows the render without changing what a node looks like."""

    async def _seed(self, client, tmp_test_dir, roles=("user", "assistant", "user", "assistant")):
        chat = await create_chat(client, title="Narrowed")
        db_path = os.path.join(tmp_test_dir, "test.db")
        ids = [
            await _seed_message(db_path, chat["id"], role, i, f"line {i}")
            for i, role in enumerate(roles)
        ]
        return chat, ids

    async def test_full_render_has_every_node(self, client, tmp_test_dir):
        chat, ids = await self._seed(client, tmp_test_dir)
        resp = await client.get(f"/partials/message-list/{chat['id']}")
        assert resp.status_code == 200
        for msg_id in ids:
            assert f'id="message-{msg_id}"' in resp.text
        assert f'data-order="{",".join(ids)}"' in resp.text

    async def test_narrowed_render_keeps_the_global_index(self, client, tmp_test_dir):
        chat, ids = await self._seed(client, tmp_test_dir)
        resp = await client.get(f"/partials/message-list/{chat['id']}?ids={ids[1]}")
        assert resp.status_code == 200

        assert f'id="message-{ids[1]}"' in resp.text
        assert f'id="message-{ids[0]}"' not in resp.text
        assert f'id="message-{ids[3]}"' not in resp.text
        assert re.search(
            rf'data-message-id="{ids[1]}"[^>]*data-msg-index="2"', resp.text
        ), "a narrowed node must keep its position in the whole list"

        assert f'data-order="{",".join(ids)}"' in resp.text, "the order stays complete"

    async def test_narrowed_render_keeps_the_latest_flag(self, client, tmp_test_dir):
        chat, ids = await self._seed(client, tmp_test_dir)

        mid = await client.get(f"/partials/message-list/{chat['id']}?ids={ids[1]}")
        latest = await client.get(f"/partials/message-list/{chat['id']}?ids={ids[3]}")

        assert "actionTriggerRegeneration" not in mid.text, (
            "a message that is not last must not look like the latest one"
        )
        assert "actionTriggerRegeneration" in latest.text
