import json
import re

from tests.helpers import create_character


def _standalone_disabled(html: str) -> int:
    return len(re.findall(r"(?m)^\s*disabled\s*$", html))


class TestGreetingSectionPartial:
    async def test_render_from_db(self, client):
        """Open with no working state falls back to the stored greetings."""
        c = await create_character(client, "G", first_mes="Hello", alternate_greetings=["Alt A"])
        resp = await client.post(f"/partials/character-greeting/{c['id']}")
        assert resp.status_code == 200
        html = resp.text
        assert 'id="edit-char-greeting-section"' in html
        assert "1/2" in html
        assert ">Hello</textarea>" in html
        assert f'value=\'{json.dumps(["Hello", "Alt A"])}\'' in html
        assert 'name="greeting_idx" value="0"' in html

    async def test_render_empty_db(self, client):
        c = await create_character(client, "NoGreet")
        resp = await client.post(f"/partials/character-greeting/{c['id']}")
        assert "0/0" in resp.text
        assert _standalone_disabled(resp.text) == 3

    async def test_render_not_found(self, client):
        resp = await client.post("/partials/character-greeting/nonexistent")
        assert resp.status_code == 404

    async def test_next_merges_current_value(self, client):
        """Nav posts the working list + current textarea; the server merges the
        edited value into the list before moving to the next variant."""
        c = await create_character(client, "G", first_mes="Hello", alternate_greetings=["Alt A"])
        resp = await client.post(
            f"/partials/character-greeting/{c['id']}",
            data={
                "action": "next",
                "greeting": "Edited Hello",
                "greetings_json": json.dumps(["Hello", "Alt A"]),
                "greeting_idx": "0",
            },
        )
        html = resp.text
        assert "2/2" in html
        assert ">Alt A</textarea>" in html
        assert json.dumps(["Edited Hello", "Alt A"]) in html

    async def test_prev_clamps_at_first(self, client):
        c = await create_character(client, "G", first_mes="Hello", alternate_greetings=["Alt A"])
        resp = await client.post(
            f"/partials/character-greeting/{c['id']}",
            data={
                "action": "prev",
                "greeting": "Hello",
                "greetings_json": json.dumps(["Hello", "Alt A"]),
                "greeting_idx": "0",
            },
        )
        html = resp.text
        assert "1/2" in html
        assert ">Hello</textarea>" in html
        assert _standalone_disabled(html) == 1, "prev disabled at first variant"

    async def test_add_appends_and_focuses(self, client):
        c = await create_character(client, "G", first_mes="Hello")
        resp = await client.post(
            f"/partials/character-greeting/{c['id']}",
            data={
                "action": "add",
                "greeting": "Hello",
                "greetings_json": json.dumps(["Hello"]),
                "greeting_idx": "0",
            },
        )
        html = resp.text
        assert "2/2" in html
        assert "autofocus" in html
        assert json.dumps(["Hello", ""]) in html
        assert 'name="greeting_idx" value="1"' in html

    async def test_delete_removes_variant(self, client):
        c = await create_character(client, "G", first_mes="Hello", alternate_greetings=["Alt A", "Alt B"])
        resp = await client.post(
            f"/partials/character-greeting/{c['id']}",
            data={
                "action": "delete",
                "greeting": "Hello",
                "greetings_json": json.dumps(["Hello", "Alt A", "Alt B"]),
                "greeting_idx": "2",
            },
        )
        html = resp.text
        assert "2/2" in html
        assert json.dumps(["Hello", "Alt A"]) in html
        assert 'name="greeting_idx" value="1"' in html

    async def test_delete_last_lands_on_previous(self, client):
        c = await create_character(client, "G", first_mes="Hello")
        resp = await client.post(
            f"/partials/character-greeting/{c['id']}",
            data={
                "action": "delete",
                "greeting": "Hello",
                "greetings_json": json.dumps(["Hello"]),
                "greeting_idx": "0",
            },
        )
        html = resp.text
        assert "0/0" in html
        assert _standalone_disabled(html) == 3

    async def test_whitespace_slots_survive_navigation(self, client):
        """In-progress empty slots must survive nav — the old client kept raw
        values in the working list during the session and only filtered at
        save, so the server must too (otherwise a fresh slot typed into after
        "add" would be dropped before the merge)."""
        c = await create_character(client, "G", first_mes="Hello")
        resp = await client.post(
            f"/partials/character-greeting/{c['id']}",
            data={
                "action": "add",
                "greeting": "Hello",
                "greetings_json": json.dumps(["Hello"]),
                "greeting_idx": "0",
            },
        )
        html = resp.text
        assert "2/2" in html
        assert json.dumps(["Hello", ""]) in html

        resp = await client.post(
            f"/partials/character-greeting/{c['id']}",
            data={
                "action": "next",
                "greeting": "",
                "greetings_json": json.dumps(["Hello", ""]),
                "greeting_idx": "1",
            },
        )
        html = resp.text
        assert "2/2" in html
        assert json.dumps(["Hello", ""]) in html, "empty slot kept after navigation"
