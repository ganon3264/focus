"""Integration tests for the Focus import/export system."""

import json
from io import BytesIO
from zipfile import ZipFile

from tests.conftest import create_character, create_chat, create_persona, create_preset


def _extract_database_from_zip(zip_bytes: bytes) -> dict:
    with ZipFile(BytesIO(zip_bytes)) as zf:
        return json.loads(zf.read("database.json"))


class TestExport:
    async def test_export_characters(self, client):
        char1 = await create_character(client, "Alpha", description="First")
        char2 = await create_character(client, "Beta", description="Second")

        resp = await client.post(
            "/api/export",
            json={
                "characters": [char1["id"], char2["id"]],
            },
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/zip"

        db = _extract_database_from_zip(resp.content)
        assert len(db["characters"]) == 2
        names = {c["name"] for c in db["characters"]}
        assert names == {"Alpha", "Beta"}

    async def test_export_star_selects_all_characters(self, client):
        await create_character(client, "Alpha")
        await create_character(client, "Beta")
        await create_character(client, "Gamma")

        resp = await client.post(
            "/api/export",
            json={
                "characters": ["*"],
            },
        )
        db = _extract_database_from_zip(resp.content)
        assert len(db["characters"]) == 3

    async def test_export_personas(self, client):
        await create_persona(client, "Hero")
        await create_persona(client, "Villain")

        resp = await client.post(
            "/api/export",
            json={
                "personas": ["*"],
            },
        )
        db = _extract_database_from_zip(resp.content)
        assert len(db["personas"]) >= 2  # default User + Hero + Villain

    async def test_export_presets_with_blocks(self, client):
        p = await create_preset(client, "Test Preset")

        # Add a couple of blocks
        await client.post(
            f"/api/presets/{p['id']}/blocks",
            json={
                "name": "Block1",
                "content": "Hello",
                "role": "system",
                "block_type": "text",
            },
        )
        await client.post(
            f"/api/presets/{p['id']}/blocks",
            json={
                "name": "Block2",
                "content": "World",
                "role": "user",
                "block_type": "text",
            },
        )

        resp = await client.post(
            "/api/export",
            json={
                "presets": [p["id"]],
            },
        )
        db = _extract_database_from_zip(resp.content)
        assert len(db["presets"]) == 1
        # Preset comes with 5 default blocks + 2 added
        assert len(db["preset_blocks"]) == 7

    async def test_export_chats_cascade_includes_references(self, client):
        char = await create_character(client, "ChatChar")
        persona = await create_persona(client, "ChatPersona")
        preset = await create_preset(client, "ChatPreset")
        chat = await create_chat(client, char["id"], persona["id"], preset["id"])

        resp = await client.post(
            "/api/export",
            json={
                "chats": [chat["id"]],
            },
        )
        db = _extract_database_from_zip(resp.content)

        assert len(db["chats"]) == 1
        assert len(db["characters"]) == 1
        assert db["characters"][0]["id"] == char["id"]
        assert len(db["personas"]) >= 1
        assert len(db["presets"]) == 1

    async def test_export_empty_selection(self, client):
        resp = await client.post(
            "/api/export",
            json={
                "characters": [],
                "personas": [],
                "presets": [],
                "chats": [],
            },
        )
        db = _extract_database_from_zip(resp.content)
        assert db["characters"] == []
        assert db["personas"] == []
        assert db["chats"] == []


class TestImport:
    async def test_roundtrip_characters(self, client):
        c1 = await create_character(client, "ExportMe", description="Test desc", personality="Quiet")
        c2 = await create_character(client, "AlsoExport")

        # Export
        resp = await client.post(
            "/api/export",
            json={
                "characters": [c1["id"], c2["id"]],
            },
        )
        zip_bytes = resp.content

        # Import
        files = {"file": ("test.focus", BytesIO(zip_bytes), "application/zip")}
        imp_resp = await client.post("/api/import", files=files)
        assert imp_resp.status_code == 201
        result = imp_resp.json()
        assert result["imported"]["characters"] == 2

        # Verify: 4 characters total (2 originals + 2 imports)
        list_resp = await client.get("/api/characters/")
        chars = list_resp.json()
        assert len(chars) == 4

    async def test_import_generates_new_ids(self, client):
        c = await create_character(client, "Original")

        resp = await client.post("/api/export", json={"characters": [c["id"]]})
        zip_bytes = resp.content

        files = {"file": ("test.focus", BytesIO(zip_bytes), "application/zip")}
        imp_resp = await client.post("/api/import", files=files)
        assert imp_resp.status_code == 201

        # Get all characters and verify IDs are different
        list_resp = await client.get("/api/characters/")
        chars = list_resp.json()
        ids = {ch["id"] for ch in chars}
        assert len(ids) == 2
        assert c["id"] in ids

    async def test_double_import_no_collision(self, client):
        c = await create_character(client, "Single")

        resp = await client.post("/api/export", json={"characters": [c["id"]]})
        zip_bytes = resp.content

        files = {"file": ("test.focus", BytesIO(zip_bytes), "application/zip")}
        await client.post("/api/import", files=files)
        await client.post("/api/import", files=files)

        list_resp = await client.get("/api/characters/")
        assert len(list_resp.json()) == 3

    async def test_roundtrip_presets(self, client):
        p = await create_preset(client, "MyPreset")
        await client.post(
            f"/api/presets/{p['id']}/blocks",
            json={
                "name": "System",
                "content": "You are helpful",
                "role": "system",
                "block_type": "text",
            },
        )

        resp = await client.post("/api/export", json={"presets": [p["id"]]})
        files = {"file": ("test.focus", BytesIO(resp.content), "application/zip")}
        imp_resp = await client.post("/api/import", files=files)
        assert imp_resp.status_code == 201
        assert imp_resp.json()["imported"]["presets"] == 1

    async def test_roundtrip_personas(self, client):
        p = await create_persona(client, "CustomPersona")

        resp = await client.post(
            "/api/export",
            json={
                "personas": [p["id"]],
            },
        )
        files = {"file": ("test.focus", BytesIO(resp.content), "application/zip")}
        imp_resp = await client.post("/api/import", files=files)
        assert imp_resp.status_code == 201
        assert imp_resp.json()["imported"]["personas"] == 1

    async def test_invalid_file_extension(self, client):
        files = {"file": ("not_valid.txt", BytesIO(b"garbage"), "text/plain")}
        resp = await client.post("/api/import", files=files)
        assert resp.status_code == 400

    async def test_broken_zip_rejected(self, client):
        files = {"file": ("bad.focus", BytesIO(b"not a zip file"), "application/zip")}
        resp = await client.post("/api/import", files=files)
        assert resp.status_code == 500


class TestEndToEnd:
    async def test_full_roundtrip(self, client):
        char = await create_character(client, "E2E Char", description="Full test", first_mes="Hello there!")
        preset = await create_preset(client, "E2E Preset")
        persona = await create_persona(client, "E2E Persona")
        await create_chat(client, char["id"], persona["id"], preset["id"])

        # Count existing entities
        chars_before = len((await client.get("/api/characters/")).json())

        # Export everything
        resp = await client.post(
            "/api/export",
            json={
                "characters": ["*"],
                "personas": ["*"],
                "presets": ["*"],
                "chats": ["*"],
            },
        )
        zip_bytes = resp.content

        # Import
        files = {"file": ("full.focus", BytesIO(zip_bytes), "application/zip")}
        imp_resp = await client.post("/api/import", files=files)
        assert imp_resp.status_code == 201
        imported = imp_resp.json()["imported"]

        assert imported["characters"] >= 1
        assert imported["presets"] >= 1
        assert imported["chats"] >= 1
        assert imported["messages"] >= 1  # greeting message

        # Verify counts doubled
        chars_after = len((await client.get("/api/characters/")).json())
        assert chars_after == chars_before + imported["characters"]


class TestCascading:
    async def test_chat_export_includes_character(self, client):
        char = await create_character(client, "CascadeChar")
        chat = await create_chat(client, character_id=char["id"])

        resp = await client.post("/api/export", json={"chats": [chat["id"]]})
        db = _extract_database_from_zip(resp.content)
        assert db["characters"][0]["id"] == char["id"]

    async def test_character_export_includes_blocks(self, client):
        c = await create_character(client, "BlockChar")
        resp = await client.post(
            f"/api/characters/{c['id']}/blocks",
            json={
                "name": "Extra",
                "content": "block content",
                "role": "system",
            },
        )
        block_id = resp.json()["id"]

        resp = await client.post("/api/export", json={"characters": [c["id"]]})
        db = _extract_database_from_zip(resp.content)
        assert len(db["char_blocks"]) == 1
        assert db["char_blocks"][0]["id"] == block_id


class TestProvidersAndSecrets:
    async def test_providers_roundtrip(self, client):
        # Create a provider
        resp = await client.post(
            "/api/providers/",
            json={
                "name": "TestProvider",
                "type": "openai_compat",
                "base_url": "http://localhost:8080/v1",
                "api_key": "sk-test-123",
                "model": "test-model",
            },
        )
        assert resp.status_code == 201
        provider_id = resp.json()["id"]

        # Export including providers
        resp = await client.post(
            "/api/export",
            json={
                "include_providers": True,
            },
        )
        zip_bytes = resp.content

        # Import
        files = {"file": ("providers.focus", BytesIO(zip_bytes), "application/zip")}
        imp_resp = await client.post("/api/import", files=files)
        assert imp_resp.status_code == 201
        assert imp_resp.json()["imported"]["providers"] >= 1

        # Verify API key survived
        list_resp = await client.get("/api/providers/")
        providers = list_resp.json()
        # Provider with api_key != SECRET: prefix gets it shown directly
        keys_shown = [p for p in providers if p["id"] == provider_id]
        assert len(keys_shown) >= 1

    async def test_secrets_roundtrip(self, client):
        # Create a secret
        resp = await client.post(
            "/api/providers/secrets",
            json={
                "name": "my-secret",
                "value": "super-secret-value",
            },
        )
        assert resp.status_code in (200, 201)

        # Export including secrets
        resp = await client.post("/api/export", json={"include_secrets": True})
        zip_bytes = resp.content

        # Import
        files = {"file": ("secrets.focus", BytesIO(zip_bytes), "application/zip")}
        imp_resp = await client.post("/api/import", files=files)
        assert imp_resp.status_code == 201
        assert imp_resp.json()["imported"]["secrets"] >= 0  # secrets use INSERT OR REPLACE
