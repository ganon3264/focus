import base64
import json
import struct
import zlib

from tests.helpers import create_character, create_chat


def _minimal_png(text_keyword: bytes, text_value: bytes) -> bytes:
    """Build a minimal valid PNG with a single tEXt chunk."""
    chunk_payload = text_keyword + b"\x00" + text_value
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr_chunk = struct.pack(">I", 13) + b"IHDR" + ihdr_data + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data) & 0xFFFFFFFF)
    meta_len = struct.pack(">I", len(chunk_payload))
    meta_crc = struct.pack(">I", zlib.crc32(b"tEXt" + chunk_payload) & 0xFFFFFFFF)
    iend_crc = struct.pack(">I", zlib.crc32(b"IEND") & 0xFFFFFFFF)
    return b"".join([signature, ihdr_chunk, meta_len, b"tEXt", chunk_payload, meta_crc, b"\x00\x00\x00\x00IEND", iend_crc])


def _png_card(card_dict: dict) -> bytes:
    """Encode a character card dict into a PNG PNG."""
    raw = base64.b64encode(json.dumps(card_dict).encode("latin-1")).decode("latin-1")
    return _minimal_png(b"chara", raw.encode("latin-1"))


def _png_v3_card(card_dict: dict) -> bytes:
    """Encode a V3 character card dict into a PNG with a ``ccv3`` chunk."""
    raw = base64.b64encode(json.dumps(card_dict).encode("latin-1")).decode("latin-1")
    return _minimal_png(b"ccv3", raw.encode("latin-1"))


class TestCharacters:
    async def test_list_empty(self, client):
        resp = await client.get("/api/characters/")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_create(self, client):
        resp = await client.post(
            "/api/characters/",
            json={
                "name": "Sylvie",
                "description": "A fox",
                "personality": "Clever",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data
        assert data["name"] == "Sylvie"

    async def test_list_after_create(self, client):
        await create_character(client, "A")
        await create_character(client, "B")
        resp = await client.get("/api/characters/")
        assert len(resp.json()) == 2

    async def test_get_by_id(self, client):
        c = await create_character(client, "Char1", description="Test desc")
        resp = await client.get(f"/api/characters/{c['id']}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Char1"
        card = data["card"]
        assert card["data"]["description"] == "Test desc"

    async def test_get_not_found(self, client):
        resp = await client.get("/api/characters/nonexistent")
        assert resp.status_code == 404

    async def test_update(self, client):
        c = await create_character(client, "Original")
        await client.patch(
            f"/api/characters/{c['id']}",
            json={
                "name": "Renamed",
                "personality": "Grumpy",
            },
        )
        resp = await client.get(f"/api/characters/{c['id']}")
        card = resp.json()["card"]
        assert card["data"]["name"] == "Renamed"
        assert card["data"]["personality"] == "Grumpy"
        assert card["data"]["description"] == "Desc"

    async def test_soft_delete_and_trash(self, client):
        c = await create_character(client, "Deletable")
        await client.delete(f"/api/characters/{c['id']}")

        resp = await client.get("/api/characters/")
        assert len(resp.json()) == 0

        resp = await client.get("/api/characters/trash")
        assert len(resp.json()) == 1

    async def test_restore(self, client):
        c = await create_character(client, "Restorable")
        await client.delete(f"/api/characters/{c['id']}")
        await client.post(f"/api/characters/{c['id']}/restore")

        resp = await client.get("/api/characters/")
        assert len(resp.json()) == 1

    async def test_hard_delete(self, client):
        c = await create_character(client, "HardDelete")
        await client.delete(f"/api/characters/{c['id']}?hard=true")

        resp = await client.get(f"/api/characters/{c['id']}")
        assert resp.status_code == 404


class TestCharacterLifecycle:
    async def test_set_character_on_chat(self, client):
        ch = await create_chat(client)
        c = await create_character(client, "Alice")

        resp = await client.patch(f"/api/chats/{ch['id']}", json={"character_id": c["id"]})
        assert resp.status_code == 200

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["character_id"] == c["id"]

    async def test_hard_delete_character_orphans_chat(self, client):
        c = await create_character(client, "Bob")
        ch = await create_chat(client, character_id=c["id"])

        await client.delete(f"/api/characters/{c['id']}?hard=true")

        chat = await client.get(f"/api/chats/{ch['id']}")
        assert chat.json()["character_id"] is None


class TestCharacterModals:
    async def test_modal_highlights_current(self, client):
        c1 = await create_character(client, "Alice")
        c2 = await create_character(client, "Bob")

        resp = await client.get(f"/partials/characters-modal?current_character_id={c1['id']}")
        assert resp.status_code == 200
        html = resp.text

        assert 'class="card active"' in html
        assert f'id="char-card-{c1["id"]}"' in html
        assert f'id="char-card-{c2["id"]}"' in html

    async def test_modal_no_current_no_highlight(self, client):
        await create_character(client, "Alice")
        resp = await client.get("/partials/characters-modal")
        assert resp.status_code == 200
        assert 'class="card active"' not in resp.text


class TestCharacterImport:
    async def test_import_png(self, client):
        card = {"name": "Imported", "description": "From PNG"}
        png_data = _png_card(card)
        resp = await client.post(
            "/api/characters/import",
            files={"files": ("test.png", png_data, "image/png")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 1
        assert len(data["imported"]) == 1
        assert data["imported"][0]["name"] == "Imported"

    async def test_import_json(self, client):
        card = {"name": "JSON Char", "description": "From JSON"}
        json_bytes = json.dumps(card).encode("utf-8")
        resp = await client.post(
            "/api/characters/import",
            files={"files": ("test.json", json_bytes, "application/json")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["imported"]) == 1
        assert data["imported"][0]["name"] == "JSON Char"

    async def test_import_corrupt_png_returns_error(self, client):
        resp = await client.post(
            "/api/characters/import",
            files={"files": ("corrupt.png", b"not a png", "image/png")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 1
        assert len(data["imported"]) == 0
        assert len(data["errors"]) == 1
        assert "Not a valid PNG" in data["errors"][0]["error"]

    async def test_import_partial_success(self, client):
        good_card = {"name": "Good"}
        bad_data = b"not a png"
        resp = await client.post(
            "/api/characters/import",
            files=[
                ("files", ("good.png", _png_card(good_card), "image/png")),
                ("files", ("bad.png", bad_data, "image/png")),
            ],
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 2
        assert len(data["imported"]) == 1
        assert len(data["errors"]) == 1

    async def test_import_warns_on_missing_name(self, client):
        card = {"description": "No name"}
        png_data = _png_card(card)
        resp = await client.post(
            "/api/characters/import",
            files={"files": ("noname.png", png_data, "image/png")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["imported"]) == 1
        assert "warnings" in data["imported"][0]
        assert any("Missing" in w for w in data["imported"][0]["warnings"])

    async def test_import_warns_on_non_string_field(self, client):
        card = {"name": "X", "description": 42}
        png_data = _png_card(card)
        resp = await client.post(
            "/api/characters/import",
            files={"files": ("badtype.png", png_data, "image/png")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["imported"]) == 1
        assert "warnings" in data["imported"][0]
        assert any("description" in w for w in data["imported"][0]["warnings"])

    async def test_import_v3_png(self, client):
        card = {"spec": "chara_card_v3", "spec_version": "3.0", "data": {"name": "V3 Char"}}
        png_data = _png_v3_card(card)
        resp = await client.post(
            "/api/characters/import",
            files={"files": ("v3.png", png_data, "image/png")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["total"] == 1
        assert len(data["imported"]) == 1
        assert data["imported"][0]["name"] == "V3 Char"
        assert "warnings" not in data["imported"][0]

    async def test_import_v3_future_version_warns(self, client):
        card = {"spec": "chara_card_v3", "spec_version": "3.5", "data": {"name": "Future"}}
        png_data = _png_v3_card(card)
        resp = await client.post(
            "/api/characters/import",
            files={"files": ("future.png", png_data, "image/png")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data["imported"]) == 1
        assert "warnings" in data["imported"][0]
        assert any("newer" in w for w in data["imported"][0]["warnings"])
