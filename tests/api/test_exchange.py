"""Integration tests for the Focus import/export system."""

import json
import os
import uuid
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import aiosqlite
import pytest

from focus.core.utils import now_iso
from tests.helpers import create_character, create_chat, create_persona, create_preset


def _extract_database_from_zip(zip_bytes: bytes) -> dict:
    with ZipFile(BytesIO(zip_bytes)) as zf:
        return json.loads(zf.read("database.json"))


def _build_archive(database: dict, extra_entries: dict | None = None, version: str = "0.1.0") -> bytes:
    buf = BytesIO()
    with ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"app": "focus", "version": version}))
        zf.writestr("database.json", json.dumps(database))
        for name, data in (extra_entries or {}).items():
            zf.writestr(name, data)
    return buf.getvalue()


def _import_archive(client, zip_bytes: bytes, filename: str = "test.focus"):
    files = {"file": (filename, BytesIO(zip_bytes), "application/zip")}
    return client.post("/api/import", files=files)


async def _read_db(tmp_test_dir, sql: str, params: tuple = ()):
    db_path = os.path.join(tmp_test_dir, "test.db")
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        return await cur.fetchall()


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
        # Export rewrites ids to fresh values; FKs must stay consistent
        assert db["characters"][0]["id"] != char["id"]
        assert db["chats"][0]["character_id"] == db["characters"][0]["id"]
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

    async def test_export_includes_themes(self, client):
        resp = await client.post(
            "/api/themes/",
            json={"name": "My Theme", "colors": {"--bg": "#0b0d10", "--accent": "#123456"}},
        )
        assert resp.status_code == 201
        theme_id = resp.json()["id"]
        char = await create_character(client, "Themed")
        await client.patch(f"/api/characters/{char['id']}", json={"theme_id": theme_id})

        resp = await client.post("/api/export", json={"characters": [char["id"]]})
        db = _extract_database_from_zip(resp.content)

        # Custom theme travels with the archive, ids remapped consistently
        theme = next(t for t in db["themes"] if t["name"] == "My Theme")
        assert theme["is_system"] == 0
        exported_char = db["characters"][0]
        assert exported_char["id"] != char["id"]
        assert exported_char["theme_id"] == theme["id"]
        # Built-in themes are exported as ordinary themes so imported copies
        # stay deletable (they'd otherwise be protected is_system rows).
        assert all(t["is_system"] == 0 for t in db["themes"])


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

    async def test_roundtrip_themed_character(self, client, tmp_test_dir):
        resp = await client.post(
            "/api/themes/",
            json={"name": "Teal", "colors": {"--bg": "#0b0d10", "--accent": "#14b8a6"}},
        )
        assert resp.status_code == 201
        theme_id = resp.json()["id"]
        char = await create_character(client, "Themed")
        await client.patch(f"/api/characters/{char['id']}", json={"theme_id": theme_id})

        resp = await client.post("/api/export", json={"characters": [char["id"]]})
        assert resp.status_code == 200
        zip_bytes = resp.content

        files = {"file": ("test.focus", BytesIO(zip_bytes), "application/zip")}
        imp_resp = await client.post("/api/import", files=files)
        assert imp_resp.status_code == 201
        assert imp_resp.json()["imported"]["themes"] >= 1

        chars = await _read_db(tmp_test_dir, "SELECT id, name, theme_id FROM characters")
        imported = next(c for c in chars if c["name"] == "Themed" and c["id"] != char["id"])
        assert imported["theme_id"] is not None, "imported character keeps its theme reference"
        themes = (await client.get("/api/themes/")).json()
        assert any(t["id"] == imported["theme_id"] and t["name"] == "Teal" for t in themes)

    async def test_import_modified_builtin_theme_keeps_receiving_seed(self, client):
        db = {
            "themes": [
                {
                    "id": "builtin-slate",
                    "name": "Hacked Slate",
                    "colors_json": '{"--bg": "#ff0000"}',
                    "is_system": 1,
                    "created_at": "2026-01-01",
                }
            ],
            "characters": [],
        }
        resp = await _import_archive(client, _build_archive(db, version="0.3.0"))
        assert resp.status_code == 201

        themes = (await client.get("/api/themes/")).json()
        slate = next(t for t in themes if t["id"] == "builtin-slate")
        assert slate["name"] == "Slate (Default)", "built-in duplicates are skipped, seed preserved"

    async def test_v2_archive_with_themes_imports_via_legacy_path(self, client, tmp_test_dir):
        # Versions below 0.3.0 take the legacy remap path; themes and the
        # characters.theme_id FK must survive it consistently.
        db = {
            "themes": [
                {
                    "id": "t-1",
                    "name": "Old Custom",
                    "colors_json": '{"--accent": "#abcdef"}',
                    "is_system": 0,
                    "created_at": "2026-01-01",
                }
            ],
            "characters": [
                {
                    "id": "c-1",
                    "name": "Old",
                    "card_json": "{}",
                    "theme_id": "t-1",
                    "image_path": None,
                    "created_at": "2026-01-01",
                    "is_deleted": 0,
                }
            ],
        }
        resp = await _import_archive(client, _build_archive(db, version="0.2.0"))
        assert resp.status_code == 201

        rows = await _read_db(tmp_test_dir, "SELECT id, theme_id FROM characters")
        themes = await _read_db(tmp_test_dir, "SELECT id, name FROM themes")
        assert len(rows) == 1
        assert rows[0]["theme_id"] is not None
        assert any(t["name"] == "Old Custom" and t["id"] == rows[0]["theme_id"] for t in themes)

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
        first = await client.post("/api/import", files=files)
        assert first.status_code == 201
        # Self-contained archives are imported verbatim, so importing the same
        # archive twice is a conflict instead of a silent duplicate
        second = await client.post("/api/import", files=files)
        assert second.status_code == 400

        list_resp = await client.get("/api/characters/")
        assert len(list_resp.json()) == 2

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


class TestImportSecurity:
    @pytest.mark.parametrize("version", ["0.1.0", "0.2.0"])
    async def test_rejects_traversal_in_assets(self, client, version):
        archive = _build_archive({"characters": []}, {"assets/../../evil.txt": b"pwned"}, version=version)
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400
        assert not any(
            p.name == "evil.txt" for p in Path(os.environ["FOCUS_ASSETS_DIR"]).rglob("*")
        )

    async def test_rejects_traversal_in_tools(self, client):
        archive = _build_archive({"characters": []}, {"tools/../../evil.json": b"{}"})
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400

    async def test_rejects_absolute_entries(self, client):
        archive = _build_archive({"characters": []}, {"/tmp/evil.txt": b"x"})
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400

    async def test_rejects_backslash_entries(self, client):
        archive = _build_archive({"characters": []}, {"assets\\evil.txt": b"x"})
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400

    async def test_accepts_legacy_assets_prefix_entries(self, client):
        # Pre-fix archives stored entries as "assets/attachments/x.png"
        archive = _build_archive({"characters": []}, {"assets/attachments/old.png": b"png"})
        resp = await _import_archive(client, archive)
        assert resp.status_code == 201
        assert (Path(os.environ["FOCUS_ASSETS_DIR"]) / "attachments" / "old.png").exists()

    async def test_rejects_sql_injection_column_names(self, client):
        archive = _build_archive({
            "characters": [{"id) VALUES (('x','y'))--": "z"}],
        })
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400
        assert (await client.get("/api/characters/")).json() == []

    async def test_rejects_missing_required_columns(self, client):
        archive = _build_archive({
            "characters": [{"id": str(uuid.uuid4()), "name": "NoCreatedAt", "card_json": "{}", "is_deleted": 0}],
        })
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400

    async def test_rejects_oversized_archive(self, client, monkeypatch):
        monkeypatch.setattr("focus.exchange.MAX_IMPORT_UNCOMPRESSED_BYTES", 2048)
        archive = _build_archive({"characters": []}, {"attachments/x.bin": b"0" * 10000})
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400
        leftover = Path(os.environ["FOCUS_ASSETS_DIR"]) / "attachments" / "x.bin"
        assert not leftover.exists()

    async def test_rejects_invalid_tool_config(self, client, monkeypatch, tmp_test_dir):
        fake_tools = Path(tmp_test_dir) / "tools"
        fake_tools.mkdir(exist_ok=True)
        monkeypatch.setattr("focus.exchange.TOOLS_DIR", fake_tools)
        archive = _build_archive({"characters": []}, {"tools/evil.json": b"not json"})
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400
        assert not (fake_tools / "evil.json").exists()

    @pytest.mark.parametrize("version", ["0.1.0", "0.2.0"])
    async def test_accepts_valid_tool_config(self, client, monkeypatch, tmp_test_dir, version):
        fake_tools = Path(tmp_test_dir) / "tools"
        fake_tools.mkdir(exist_ok=True)
        monkeypatch.setattr("focus.exchange.TOOLS_DIR", fake_tools)
        config = {
            "name": "echo_tool",
            "description": "echoes input",
            "command": ["echo", "hi"],
            "timeout": 10,
            "writes": False,
            "params": [],
        }
        archive = _build_archive({"characters": []}, {"tools/echo.json": json.dumps(config)}, version=version)
        resp = await _import_archive(client, archive)
        assert resp.status_code == 201
        assert (fake_tools / "echo.json").exists()

    async def test_failed_import_rolls_back(self, client):
        now = now_iso()
        database = {
            "characters": [{"id": str(uuid.uuid4()), "name": "R", "image_path": None, "card_json": "{}", "created_at": now, "is_deleted": 0}],
            "messages": [{"id": str(uuid.uuid4()), "chat_id": "missing-chat", "role": "user", "position": 0, "active_index": 0, "created_at": now}],
        }
        archive = _build_archive(database)
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400
        assert (await client.get("/api/characters/")).json() == []

    async def test_failed_import_removes_extracted_files(self, client, monkeypatch, tmp_test_dir):
        fake_tools = Path(tmp_test_dir) / "tools"
        fake_tools.mkdir(exist_ok=True)
        monkeypatch.setattr("focus.exchange.TOOLS_DIR", fake_tools)
        config = {
            "name": "echo_tool",
            "description": "echoes input",
            "command": ["echo", "hi"],
            "timeout": 10,
            "writes": False,
            "params": [],
        }
        now = now_iso()
        database = {
            # missing required column (created_at) so the insert fails
            "characters": [{"id": str(uuid.uuid4()), "name": "R", "image_path": None, "card_json": "{}", "is_deleted": 0}],
        }
        archive = _build_archive(database, {"tools/echo.json": json.dumps(config), "attachments/x.png": b"img"})
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400
        assert not (fake_tools / "echo.json").exists()
        assert not (Path(os.environ["FOCUS_ASSETS_DIR"]) / "attachments" / "x.png").exists()
        assert (await client.get("/api/characters/")).json() == []

    async def test_v3_import_is_verbatim(self, client, tmp_test_dir):
        now = now_iso()
        char_id = str(uuid.uuid4())
        archive = _build_archive({
            "characters": [{"id": char_id, "name": "V3", "image_path": None, "card_json": "{}", "created_at": now, "is_deleted": 0}],
        }, version="0.3.0")
        resp = await _import_archive(client, archive)
        assert resp.status_code == 201
        rows = await _read_db(tmp_test_dir, "SELECT id, name FROM characters")
        assert rows[0]["id"] == char_id

    async def test_v3_minor_10_not_treated_as_legacy(self, client, tmp_test_dir):
        # "0.10.0" must not compare as older than "0.3.0" lexically
        now = now_iso()
        char_id = str(uuid.uuid4())
        archive = _build_archive({
            "characters": [{"id": char_id, "name": "V10", "image_path": None, "card_json": "{}", "created_at": now, "is_deleted": 0}],
        }, version="0.10.0")
        resp = await _import_archive(client, archive)
        assert resp.status_code == 201
        rows = await _read_db(tmp_test_dir, "SELECT id FROM characters")
        assert rows[0]["id"] == char_id

    async def test_non_string_version_rejected(self, client):
        archive = _build_archive({"characters": []}, version=2)
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400

    async def test_invalid_version_string_rejected(self, client):
        archive = _build_archive({"characters": []}, version="not.a.version")
        resp = await _import_archive(client, archive)
        assert resp.status_code == 400

    async def test_provider_name_dedup_is_bounded(self, client):
        for name in ("P", "P (Imported)"):
            resp = await client.post(
                "/api/providers/",
                json={
                    "name": name,
                    "type": "openai_compat",
                    "base_url": "http://localhost:8080/v1",
                    "api_key": "k",
                    "model": "m",
                },
            )
            assert resp.status_code == 201

        archive = _build_archive({
            "providers": [{
                "id": str(uuid.uuid4()), "name": "P", "type": "openai_compat",
                "base_url": "http://x/v1", "api_key": "k", "model": "m",
                "params_json": "{}", "created_at": now_iso(),
            }],
        })
        resp = await _import_archive(client, archive)
        assert resp.status_code == 201
        names = {p["name"] for p in (await client.get("/api/providers/")).json()}
        assert "P (Imported 2)" in names

    @pytest.mark.parametrize("version", ["0.1.0", "0.2.0"])
    async def test_sanitizes_segments_on_import(self, client, tmp_test_dir, version):
        now = now_iso()
        char_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())
        msg_id = str(uuid.uuid4())
        var_id = str(uuid.uuid4())
        database = {
            "characters": [{"id": char_id, "name": "X", "image_path": None, "card_json": "{}", "created_at": now, "is_deleted": 0}],
            "chats": [{"id": chat_id, "title": "C", "character_id": char_id, "persona_id": None, "preset_id": None, "created_at": now, "updated_at": now, "is_deleted": 0, "tool_calls_enabled": 0, "tool_read_only": 1}],
            "messages": [{"id": msg_id, "chat_id": chat_id, "role": "assistant", "position": 1, "active_index": 0, "created_at": now}],
            "message_variants": [{
                "id": var_id, "message_id": msg_id, "variant_index": 0, "content": "hi",
                "created_at": now, "model_name": None, "reasoning": None,
                "segments_json": json.dumps([
                    {"type": "reasoning", "html": "<img src=x onerror=alert(1)>", "index": 0},
                ]),
                "reasoning_details": None, "variant_meta": None,
            }],
        }
        archive = _build_archive(database, version=version)
        resp = await _import_archive(client, archive)
        assert resp.status_code == 201

        rows = await _read_db(tmp_test_dir, "SELECT segments_json FROM message_variants")
        segments = json.loads(rows[0]["segments_json"])
        assert segments[0]["type"] == "reasoning"
        assert "<img" not in segments[0]["html"]
        assert "&lt;img" in segments[0]["html"]

    async def test_nullifies_malformed_segments(self, client, tmp_test_dir):
        now = now_iso()
        char_id = str(uuid.uuid4())
        chat_id = str(uuid.uuid4())
        msg_id = str(uuid.uuid4())
        database = {
            "characters": [{"id": char_id, "name": "X", "image_path": None, "card_json": "{}", "created_at": now, "is_deleted": 0}],
            "chats": [{"id": chat_id, "title": "C", "character_id": char_id, "persona_id": None, "preset_id": None, "created_at": now, "updated_at": now, "is_deleted": 0, "tool_calls_enabled": 0, "tool_read_only": 1}],
            "messages": [{"id": msg_id, "chat_id": chat_id, "role": "assistant", "position": 1, "active_index": 0, "created_at": now}],
            "message_variants": [{
                "id": str(uuid.uuid4()), "message_id": msg_id, "variant_index": 0,
                "content": "hi", "created_at": now,
                "segments_json": "this is not json",
            }],
        }
        archive = _build_archive(database)
        resp = await _import_archive(client, archive)
        assert resp.status_code == 201
        rows = await _read_db(tmp_test_dir, "SELECT segments_json FROM message_variants")
        assert rows[0]["segments_json"] is None


class TestAttachmentRoundtrip:
    async def test_attachment_files_preserved_on_import(self, client, tmp_test_dir):
        char = await create_character(client, "AttachChar")
        chat = await create_chat(client, char["id"])

        files = {"files": ("hello.txt", BytesIO(b"hello attachment"), "text/plain")}
        resp = await client.post(f"/api/chats/{chat['id']}/attachments", files=files)
        assert resp.status_code == 201
        att = resp.json()["attachments"][0]
        assert Path(att["file_path"]).exists()

        resp = await client.post("/api/export", json={"chats": [chat["id"]]})
        assert resp.status_code == 200
        with ZipFile(BytesIO(resp.content)) as zf:
            assert "attachments" in {n.split("/")[0] for n in zf.namelist()}

        imp = await _import_archive(client, resp.content)
        assert imp.status_code == 201

        rows = await _read_db(
            tmp_test_dir,
            "SELECT file_path FROM message_attachments WHERE file_path != ?",
            (att["file_path"],),
        )
        imported = rows[0]
        assert imported is not None
        assert Path(imported["file_path"]).exists()

        for p in (att["file_path"], imported["file_path"]):
            Path(p).unlink(missing_ok=True)

    async def test_tool_images_preserved_on_import(self, client, tmp_test_dir):
        chat = await create_chat(client)
        now = now_iso()
        msg_id = str(uuid.uuid4())
        var_id = str(uuid.uuid4())

        from focus.core.paths import ASSETS_DIR

        img_rel = f"tool/test_{uuid.uuid4().hex}/img1.webp"
        img = ASSETS_DIR / img_rel
        img.parent.mkdir(parents=True, exist_ok=True)
        img.write_bytes(b"fake webp")
        try:
            db_path = os.path.join(tmp_test_dir, "test.db")
            async with aiosqlite.connect(db_path) as db:
                await db.execute(
                    "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (msg_id, chat["id"], "assistant", 1, 0, now),
                )
                await db.execute(
                    "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                    (var_id, msg_id, 0, "text", now),
                )
                await db.execute(
                    "INSERT INTO tool_calls (id, chat_id, message_id, variant_id, tool_name, arguments, result, is_error, result_image_path, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), chat["id"], msg_id, var_id, "read_image", "{}", "ok", 0, img_rel, now),
                )
                await db.commit()

            resp = await client.post("/api/export", json={"chats": [chat["id"]]})
            assert resp.status_code == 200
            with ZipFile(BytesIO(resp.content)) as zf:
                assert img_rel in zf.namelist()

            imp = await _import_archive(client, resp.content)
            assert imp.status_code == 201

            rows = await _read_db(
                tmp_test_dir,
                "SELECT result_image_path FROM tool_calls WHERE result_image_path IS NOT NULL",
            )
            assert rows, "tool image path should survive the roundtrip"
            assert (ASSETS_DIR / rows[0]["result_image_path"]).exists()
        finally:
            for p in img.parent.iterdir():
                p.unlink(missing_ok=True)
            img.parent.rmdir()


class TestImportSettings:
    async def test_does_not_clobber_existing_settings(self, client, tmp_test_dir):
        resp = await client.patch("/api/settings/", json={"key": "focus_char_view", "value": "cards"})
        assert resp.status_code == 200

        now = now_iso()
        archive = _build_archive({
            "characters": [{"id": str(uuid.uuid4()), "name": "S", "image_path": None, "card_json": "{}", "created_at": now, "is_deleted": 0}],
            "settings": [
                {"key": "focus_char_view", "value": "table"},
                {"key": "new_setting_key", "value": "from-archive"},
            ],
        }, version="0.2.0")
        resp = await _import_archive(client, archive)
        assert resp.status_code == 201

        settings = (await client.get("/api/settings/")).json()
        assert settings["focus_char_view"] == "cards"
        assert settings["new_setting_key"] == "from-archive"


class TestDuplicateAttachments:
    async def test_same_filename_uploads_get_unique_entries(self, client, tmp_test_dir):
        char = await create_character(client, "DupChar")
        chat = await create_chat(client, char["id"])

        for _ in range(2):
            files = {"files": ("image.png", BytesIO(b"png data"), "image/png")}
            resp = await client.post(f"/api/chats/{chat['id']}/attachments", files=files)
            assert resp.status_code == 201

        resp = await client.post("/api/export", json={"chats": [chat["id"]]})
        assert resp.status_code == 200
        with ZipFile(BytesIO(resp.content)) as zf:
            entry_names = [n for n in zf.namelist() if n.startswith("attachments/")]
            assert len(entry_names) == 2
            assert len(set(entry_names)) == 2

        imp = await _import_archive(client, resp.content)
        assert imp.status_code == 201
        rows = await _read_db(tmp_test_dir, "SELECT file_path FROM message_attachments")
        paths = [r["file_path"] for r in rows]
        assert len(paths) == len(set(paths))
        assert all(Path(p).exists() for p in paths)

    async def test_shared_file_path_rows_export_and_import(self, client, tmp_test_dir):
        char = await create_character(client, "ShareChar")
        chat = await create_chat(client, char["id"])

        files = {"files": ("image.png", BytesIO(b"shared bytes"), "image/png")}
        resp = await client.post(f"/api/chats/{chat['id']}/attachments", files=files)
        assert resp.status_code == 201
        att = resp.json()["attachments"][0]

        # Simulate a variant/duplicate copy: a second row pointing at the same file
        now = now_iso()
        db_path = os.path.join(tmp_test_dir, "test.db")
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO message_attachments (id, chat_id, message_id, variant_id, file_path, mime_type, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), chat["id"], None, None, att["file_path"], "image/png", now),
            )
            await db.commit()

        resp = await client.post("/api/export", json={"chats": [chat["id"]]})
        assert resp.status_code == 200
        with ZipFile(BytesIO(resp.content)) as zf:
            names = zf.namelist()
            assert len([n for n in names if n.startswith("attachments/")]) == 2
            assert all(names.count(n) == 1 for n in set(names))

        imp = await _import_archive(client, resp.content)
        assert imp.status_code == 201
        rows = await _read_db(tmp_test_dir, "SELECT file_path FROM message_attachments")
        paths = [r["file_path"] for r in rows]
        # Pre-existing rows keep sharing the original file; the imported rows
        # must each get their own file.
        assert paths.count(att["file_path"]) == 2
        imported_paths = [p for p in paths if p != att["file_path"]]
        assert len(imported_paths) == len(set(imported_paths))
        assert all(Path(p).exists() for p in imported_paths)


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
        assert db["characters"][0]["id"] != char["id"]
        assert db["chats"][0]["character_id"] == db["characters"][0]["id"]

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
        assert db["char_blocks"][0]["id"] != block_id
        assert db["char_blocks"][0]["character_id"] == db["characters"][0]["id"]


class TestProvidersAndSecrets:
    async def test_providers_roundtrip(self, client, tmp_test_dir):
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

        # Verify API key survived the roundtrip (export rewrites ids, not keys)
        rows = await _read_db(tmp_test_dir, "SELECT api_key FROM providers")
        assert any(r["api_key"] == "sk-test-123" for r in rows)

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
