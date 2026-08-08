"""API tests for the message/chat lifecycle and entity media operations.

Covers the chat message endpoints (edit/delete/swipe/branch/attachments),
trash/restore, tool-state updates, persona avatar + block images, and the
preset import/block management endpoints. Messages are seeded via raw SQL
(like test_stream_abort.py) since there is no create-message endpoint.
"""

import json
import os
import uuid
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import aiosqlite
from PIL import Image

from tests.helpers import create_chat, create_persona, create_preset


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _db_path(tmp_test_dir: str) -> str:
    return os.path.join(tmp_test_dir, "test.db")


async def _insert_message(
    db_path: str,
    chat_id: str,
    role: str,
    position: int,
    content: str = "",
    *,
    model_name: str | None = None,
    variant_meta: str | None = None,
    segments_json: str | None = None,
) -> tuple[str, str]:
    msg_id = str(uuid.uuid4())
    now = _now_iso()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, chat_id, role, position, 0, now),
        )
        variant_id = str(uuid.uuid4())
        await db.execute(
            "INSERT INTO message_variants (id, message_id, variant_index, content, created_at, model_name, variant_meta, segments_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (variant_id, msg_id, 0, content, now, model_name, variant_meta, segments_json),
        )
        await db.commit()
    return msg_id, variant_id


async def _add_variant(db_path: str, message_id: str, content: str) -> None:
    now = _now_iso()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), message_id, 1, content, now),
        )
        await db.commit()


async def _chat_with_messages(client, db_path: str, *, variants=0, title="Chat"):
    chat = await create_chat(client, title=title)
    user_id, _ = await _insert_message(db_path, chat["id"], "user", 0, "Hi")
    asst_id, _ = await _insert_message(db_path, chat["id"], "assistant", 1, "Old", model_name="gpt-4")
    for i in range(variants):
        await _add_variant(db_path, asst_id, f"Variant {i + 1}")
    return chat, user_id, asst_id


class TestEditMessage:
    async def test_edit_creates_variant_and_preserves_prev_model(self, client, tmp_test_dir):
        chat, _, asst_id = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.patch(
            f"/api/chats/{chat['id']}/messages/{asst_id}",
            json={"content": "Edited", "reasoning": "thoughts", "attachment_ids": []},
        )
        assert resp.status_code == 200
        assert resp.json()["variant_index"] == 1

        msg = await client.get(f"/api/chats/{chat['id']}/messages/{asst_id}")
        assert msg.status_code == 200
        data = msg.json()
        assert data["content"] == "Edited"
        assert data["reasoning"] == "thoughts"

        detail = await client.get(f"/api/chats/{chat['id']}")
        row = next(m for m in detail.json()["messages"] if m["id"] == asst_id)
        assert row["variant_count"] == 2
        assert row["content"] == "Edited"

    async def test_edit_binds_and_copies_attachments(self, client, tmp_test_dir):
        chat, _, asst_id = await _chat_with_messages(client, _db_path(tmp_test_dir))
        upload = await client.post(
            f"/api/chats/{chat['id']}/attachments",
            files=[("files", ("note.txt", b"payload", "text/plain"))],
        )
        att = upload.json()["attachments"][0]
        file_path = att["file_path"]
        assert Path(file_path).exists()

        await client.patch(
            f"/api/chats/{chat['id']}/messages/{asst_id}",
            json={"content": "v1", "attachment_ids": [att["id"]]},
        )
        await client.patch(
            f"/api/chats/{chat['id']}/messages/{asst_id}",
            json={"content": "v2", "attachment_ids": [att["id"]]},
        )

        db_path = _db_path(tmp_test_dir)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT * FROM message_attachments WHERE message_id = ?", (asst_id,))
            rows = [dict(r) for r in await cur.fetchall()]
        assert len(rows) == 2, "original + copied attachment rows must share the file"
        assert {r["file_path"] for r in rows} == {file_path}

    async def test_edit_not_found(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.patch(
            f"/api/chats/{chat['id']}/messages/nope", json={"content": "x", "attachment_ids": []}
        )
        assert resp.status_code == 404


class TestDeleteMessages:
    async def test_delete_message_and_after(self, client, tmp_test_dir):
        chat, user_id, asst_id = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.delete(f"/api/chats/{chat['id']}/messages/{asst_id}")
        assert resp.status_code == 204

        detail = await client.get(f"/api/chats/{chat['id']}")
        ids = [m["id"] for m in detail.json()["messages"]]
        assert user_id in ids and asst_id not in ids

    async def test_delete_message_not_found(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.delete(f"/api/chats/{chat['id']}/messages/nope")
        assert resp.status_code == 404

    async def test_bulk_delete(self, client, tmp_test_dir):
        chat, user_id, asst_id = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.post(
            f"/api/chats/{chat['id']}/messages/bulk_delete", json={"message_ids": [user_id, asst_id]}
        )
        assert resp.json() == {"deleted": 2}
        assert (await client.get(f"/api/chats/{chat['id']}")).json()["messages"] == []

    async def test_bulk_delete_empty(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.post(f"/api/chats/{chat['id']}/messages/bulk_delete", json={"message_ids": []})
        assert resp.json() == {"deleted": 0}


class TestSwipe:
    async def test_swipe_next_prev_and_needs_generation(self, client, tmp_test_dir):
        chat, _, asst_id = await _chat_with_messages(client, _db_path(tmp_test_dir), variants=1)

        resp = await client.post(f"/api/chats/{chat['id']}/messages/{asst_id}/swipe", data={"direction": "next"})
        assert resp.json() == {"ok": True, "variant_index": 1, "content": "Variant 1", "is_last": True}

        resp = await client.post(f"/api/chats/{chat['id']}/messages/{asst_id}/swipe", data={"direction": "next"})
        data = resp.json()
        assert data["needs_generation"] is True
        assert data["next_variant_index"] == 2

        resp = await client.post(f"/api/chats/{chat['id']}/messages/{asst_id}/swipe", data={"direction": "prev"})
        assert resp.json()["variant_index"] == 0
        assert resp.json()["content"] == "Old"

    async def test_swipe_greeting_loops_to_first(self, client, tmp_test_dir):
        chat = await create_chat(client)
        greeting_id, _ = await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hello there")
        resp = await client.post(f"/api/chats/{chat['id']}/messages/{greeting_id}/swipe", data={"direction": "next"})
        assert resp.json()["variant_index"] == 0

    async def test_swipe_not_found(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.post(f"/api/chats/{chat['id']}/messages/nope/swipe", data={"direction": "next"})
        assert resp.status_code == 404


class TestBranchChat:
    async def test_branch_copies_messages_variants_attachments_tool_calls(self, client, tmp_test_dir):
        chat, user_id, asst_id = await _chat_with_messages(client, _db_path(tmp_test_dir))
        await _add_variant(_db_path(tmp_test_dir), asst_id, "Alt response")

        upload = await client.post(
            f"/api/chats/{chat['id']}/attachments",
            files=[("files", ("f.txt", b"data", "text/plain"))],
        )
        att = upload.json()["attachments"][0]
        await client.patch(
            f"/api/chats/{chat['id']}/messages/{asst_id}",
            json={"content": "With att", "attachment_ids": [att["id"]]},
        )

        db_path = _db_path(tmp_test_dir)
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute("SELECT variant_id FROM message_attachments WHERE message_id = ?", (asst_id,))
            variant_row = await cur.fetchone()
            await db.execute(
                "INSERT INTO tool_calls (id, chat_id, message_id, variant_id, tool_name, arguments, result, is_error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), chat["id"], asst_id, variant_row[0], "read_file", '{"path": "/x"}', "contents", 0, _now_iso()),
            )
            await db.commit()

        resp = await client.post(f"/api/chats/{chat['id']}/messages/{asst_id}/branch")
        assert resp.status_code == 200
        new_chat_id = resp.json()["id"]
        assert new_chat_id != chat["id"]

        new_detail = await client.get(f"/api/chats/{new_chat_id}")
        assert new_detail.status_code == 200
        assert new_detail.json()["title"] == "Copy of Chat"

        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT role, position FROM messages WHERE chat_id = ? ORDER BY position", (new_chat_id,))
            copied_msgs = [dict(r) for r in await cur.fetchall()]
            cur = await db.execute("SELECT COUNT(*) FROM message_variants WHERE message_id IN (SELECT id FROM messages WHERE chat_id = ?)", (new_chat_id,))
            variant_count = (await cur.fetchone())[0]
            cur = await db.execute("SELECT COUNT(*) FROM tool_calls WHERE chat_id = ?", (new_chat_id,))
            tool_count = (await cur.fetchone())[0]
        assert [(m["role"], m["position"]) for m in copied_msgs] == [("user", 0), ("assistant", 1)]
        assert variant_count == 4  # user(1) + assistant originals(2) + edit variant(1)
        assert tool_count == 1

    async def test_branch_not_found(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        assert (await client.post("/api/chats/nope/messages/x/branch")).status_code == 404
        assert (await client.post(f"/api/chats/{chat['id']}/messages/nope/branch")).status_code == 404


class TestChatTrashRestore:
    async def test_soft_delete_trash_and_restore(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))

        resp = await client.delete(f"/api/chats/{chat['id']}")
        assert resp.status_code == 204
        assert (await client.get(f"/api/chats/{chat['id']}")).status_code == 404

        trash = await client.get("/api/chats/trash")
        assert any(c["id"] == chat["id"] for c in trash.json())

        resp = await client.post(f"/api/chats/{chat['id']}/restore")
        assert resp.json() == {"ok": True}
        assert (await client.get(f"/api/chats/{chat['id']}")).status_code == 200

    async def test_hard_delete(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.delete(f"/api/chats/{chat['id']}?hard=true")
        assert resp.status_code == 204
        async with aiosqlite.connect(_db_path(tmp_test_dir)) as db:
            cur = await db.execute("SELECT COUNT(*) FROM chats WHERE id = ?", (chat["id"],))
            assert (await cur.fetchone())[0] == 0

    async def test_restore_not_found(self, client):
        resp = await client.post("/api/chats/nope/restore")
        assert resp.status_code == 404


class TestChatUpdates:
    async def test_tool_states_roundtrip(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.put(f"/api/chats/{chat['id']}/tool-states", json={"read_file": True, "execute_shell": False})
        assert resp.json() == {"ok": True}
        detail = await client.get(f"/api/chats/{chat['id']}")
        assert detail.json()["tool_states"] == {"read_file": True, "execute_shell": False}

    async def test_update_chat_empty_body_ok(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        assert (await client.patch(f"/api/chats/{chat['id']}", json={})).status_code == 200

    async def test_update_chat_invalid_reference_400(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.patch(f"/api/chats/{chat['id']}", json={"character_id": "does-not-exist"})
        assert resp.status_code == 400


class TestAttachments:
    async def test_delete_attachment_removes_file_when_orphaned(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        upload = await client.post(
            f"/api/chats/{chat['id']}/attachments",
            files=[("files", ("x.txt", b"data", "text/plain"))],
        )
        att = upload.json()["attachments"][0]
        assert Path(att["file_path"]).exists()

        resp = await client.delete(f"/api/chats/{chat['id']}/attachments/{att['id']}")
        assert resp.status_code == 204
        assert not Path(att["file_path"]).exists()

    async def test_delete_shared_attachment_keeps_file(self, client, tmp_test_dir):
        chat, _, asst_id = await _chat_with_messages(client, _db_path(tmp_test_dir))
        upload = await client.post(
            f"/api/chats/{chat['id']}/attachments",
            files=[("files", ("x.txt", b"data", "text/plain"))],
        )
        att = upload.json()["attachments"][0]
        await client.patch(
            f"/api/chats/{chat['id']}/messages/{asst_id}",
            json={"content": "v1", "attachment_ids": [att["id"]]},
        )
        await client.patch(
            f"/api/chats/{chat['id']}/messages/{asst_id}",
            json={"content": "v2", "attachment_ids": [att["id"]]},
        )

        db_path = _db_path(tmp_test_dir)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute("SELECT id FROM message_attachments WHERE message_id = ?", (asst_id,))
            rows = [dict(r) for r in await cur.fetchall()]

        await client.delete(f"/api/chats/{chat['id']}/attachments/{rows[0]['id']}")
        assert Path(att["file_path"]).exists(), "shared file must survive while another row references it"
        await client.delete(f"/api/chats/{chat['id']}/attachments/{rows[1]['id']}")
        assert not Path(att["file_path"]).exists()

    async def test_delete_attachment_not_found(self, client, tmp_test_dir):
        chat, _, _ = await _chat_with_messages(client, _db_path(tmp_test_dir))
        resp = await client.delete(f"/api/chats/{chat['id']}/attachments/nope")
        assert resp.status_code == 404

    async def test_upload_attachment_chat_not_found(self, client):
        resp = await client.post(
            "/api/chats/nope/attachments", files=[("files", ("x.txt", b"data", "text/plain"))]
        )
        assert resp.status_code == 404


class TestPersonaMedia:
    async def test_avatar_upload_replaces_old(self, client, tmp_test_dir):
        p = await create_persona(client, "Pixie")
        buf = BytesIO()
        Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(buf, format="PNG")

        resp = await client.post(f"/api/personas/{p['id']}/avatar", files={"file": ("a.png", buf.getvalue(), "image/png")})
        assert resp.status_code == 200
        first_path = resp.json()["avatar_path"]
        assert Path(first_path).exists()

        resp = await client.post(f"/api/personas/{p['id']}/avatar", files={"file": ("b.jpg", buf.getvalue(), "image/jpeg")})
        assert not Path(first_path).exists()
        assert Path(resp.json()["avatar_path"]).exists()

    async def test_avatar_persona_not_found(self, client):
        buf = BytesIO()
        Image.new("RGBA", (8, 8), (0, 0, 0, 255)).save(buf, format="PNG")
        resp = await client.post("/api/personas/nope/avatar", files={"file": ("a.png", buf.getvalue(), "image/png")})
        assert resp.status_code == 404

    async def test_persona_block_image_upload_and_delete(self, client, tmp_test_dir):
        p = await create_persona(client, "Imaged")
        buf = BytesIO()
        Image.new("RGBA", (8, 8), (0, 255, 0, 255)).save(buf, format="PNG")

        resp = await client.post(
            f"/api/personas/{p['id']}/images", files={"file": ("pic.png", buf.getvalue(), "image/png")}
        )
        assert resp.status_code == 201
        img = resp.json()
        assert Path(img["image_path"]).exists()

        db_path = _db_path(tmp_test_dir)
        async with aiosqlite.connect(db_path) as db:
            cur = await db.execute("SELECT position FROM block_images WHERE id = ?", (img["id"],))
            assert (await cur.fetchone())[0] == 0
            cur = await db.execute("SELECT COUNT(*) FROM block_images WHERE block_id = ?", (p["id"],))
            assert (await cur.fetchone())[0] == 1

        resp = await client.post(
            f"/api/personas/{p['id']}/images", files={"file": ("pic2.png", buf.getvalue(), "image/png")}
        )
        assert resp.json()["position"] == 1

        assert (await client.delete(f"/api/personas/{p['id']}/images/{img['id']}")).status_code == 204
        assert not Path(img["image_path"]).exists()
        assert (await client.delete(f"/api/personas/{p['id']}/images/{img['id']}")).status_code == 404

    async def test_delete_persona_lifecycle(self, client, tmp_test_dir):
        p = await create_persona(client, "Doomed")
        buf = BytesIO()
        Image.new("RGBA", (8, 8), (0, 0, 255, 255)).save(buf, format="PNG")
        resp = await client.post(f"/api/personas/{p['id']}/avatar", files={"file": ("a.png", buf.getvalue(), "image/png")})
        avatar_path = resp.json()["avatar_path"]

        assert (await client.delete(f"/api/personas/{p['id']}")).status_code == 204
        trash = await client.get("/api/personas/trash")
        assert any(x["id"] == p["id"] for x in trash.json())
        assert (await client.get(f"/api/personas/{p['id']}")).status_code == 404

        assert (await client.post(f"/api/personas/{p['id']}/restore")).json() == {"ok": True}
        assert (await client.get(f"/api/personas/{p['id']}")).status_code == 200

        assert (await client.delete(f"/api/personas/{p['id']}?hard=true")).status_code == 204
        assert not Path(avatar_path).exists()

    async def test_delete_default_persona_blocked(self, client):
        p = await create_persona(client, "User")
        resp = await client.delete(f"/api/personas/{p['id']}")
        assert resp.status_code == 400

    async def test_delete_persona_not_found(self, client):
        assert (await client.delete("/api/personas/nope")).status_code == 404

    async def test_restore_persona_not_found(self, client):
        assert (await client.post("/api/personas/nope/restore")).status_code == 404

    async def test_update_persona_empty_body(self, client, tmp_test_dir):
        p = await create_persona(client, "Noop")
        resp = await client.patch(f"/api/personas/{p['id']}", json={})
        assert resp.json() == {"ok": True}


class TestPresetBlocks:
    async def test_block_crud_and_reorder(self, client, tmp_test_dir):
        pr = await create_preset(client, "Preset")
        detail = await client.get(f"/api/presets/{pr['id']}")
        block = next(b for b in detail.json()["blocks"] if b["block_type"] == "text")

        resp = await client.get(f"/api/presets/{pr['id']}/blocks/{block['id']}")
        assert resp.json()["id"] == block["id"]
        assert (await client.get(f"/api/presets/{pr['id']}/blocks/nope")).status_code == 404

        resp = await client.patch(f"/api/presets/{pr['id']}/blocks/{block['id']}", json={"content": "New content"})
        assert resp.json() == {"ok": True}
        assert (await client.get(f"/api/presets/{pr['id']}/blocks/{block['id']}")).json()["content"] == "New content"
        assert (await client.patch(f"/api/presets/{pr['id']}/blocks/{block['id']}", json={})).status_code == 200

        created = await client.post(
            f"/api/presets/{pr['id']}/blocks",
            json={"name": "Extra", "content": "x", "block_type": "text"},
        )
        new_block_id = created.json()["id"]

        blocks = [
            {"id": new_block_id, "position": 1.0},
            {"id": block["id"], "position": 2.0},
        ]
        resp = await client.put(f"/api/presets/{pr['id']}/blocks", json={"blocks": blocks})
        assert resp.json() == {"ok": True}

        detail = await client.get(f"/api/presets/{pr['id']}")
        by_id = {b["id"]: b["position"] for b in detail.json()["blocks"]}
        assert by_id[new_block_id] == 1.0
        assert by_id[block["id"]] == 2.0

        assert (await client.put(f"/api/presets/{pr['id']}/blocks", json={"blocks": []})).json() == {"ok": True}
        bad = await client.put(f"/api/presets/{pr['id']}/blocks", json={"blocks": [{"id": "nope", "position": 1.0}]})
        assert bad.status_code == 400

        assert (await client.delete(f"/api/presets/{pr['id']}/blocks/{new_block_id}")).status_code == 204
        assert (await client.get(f"/api/presets/{pr['id']}/blocks/{new_block_id}")).status_code == 404

    async def test_variable_block_exclusivity(self, client, tmp_test_dir):
        pr = await create_preset(client, "Vars")
        first = await client.post(
            f"/api/presets/{pr['id']}/blocks",
            json={"name": "Group", "content": "", "block_type": "variable"},
        )
        second = await client.post(
            f"/api/presets/{pr['id']}/blocks",
            json={"name": "Group: sub", "content": "", "block_type": "variable"},
        )
        assert second.json()["id"]

        detail = await client.get(f"/api/presets/{pr['id']}")
        by_id = {b["id"]: b for b in detail.json()["blocks"]}
        assert by_id[first.json()["id"]]["enabled"] == 1
        assert by_id[second.json()["id"]]["enabled"] == 0, "duplicate variable group must auto-disable"

        resp = await client.patch(
            f"/api/presets/{pr['id']}/blocks/{second.json()['id']}", json={"enabled": True}
        )
        assert resp.status_code == 200
        detail = await client.get(f"/api/presets/{pr['id']}")
        by_id = {b["id"]: b for b in detail.json()["blocks"]}
        assert by_id[first.json()["id"]]["enabled"] == 0, "enabling one group member must disable the others"
        assert by_id[second.json()["id"]]["enabled"] == 1

    async def test_block_image_upload_and_delete(self, client, tmp_test_dir):
        pr = await create_preset(client, "Imaged")
        detail = await client.get(f"/api/presets/{pr['id']}")
        block = next(b for b in detail.json()["blocks"] if b["block_type"] == "text")

        buf = BytesIO()
        Image.new("RGB", (8, 8), (1, 2, 3)).save(buf, format="PNG")
        resp = await client.post(
            f"/api/presets/{pr['id']}/blocks/{block['id']}/images",
            files={"file": ("pic.png", buf.getvalue(), "image/png")},
        )
        assert resp.status_code == 201
        img = resp.json()
        assert Path(img["image_path"]).exists()

        detail = await client.get(f"/api/presets/{pr['id']}")
        blocks = detail.json()["blocks"]
        with_img = next(b for b in blocks if b["id"] == block["id"])
        assert len(with_img["images"]) == 1
        assert with_img["images"][0]["id"] == img["id"]

        assert (await client.delete(f"/api/presets/{pr['id']}/blocks/{block['id']}/images/{img['id']}")).status_code == 204
        assert not Path(img["image_path"]).exists()

    async def test_block_image_block_not_found(self, client, tmp_test_dir):
        pr = await create_preset(client, "NoBlock")
        buf = BytesIO()
        Image.new("RGB", (8, 8)).save(buf, format="PNG")
        resp = await client.post(
            f"/api/presets/{pr['id']}/blocks/nope/images",
            files={"file": ("pic.png", buf.getvalue(), "image/png")},
        )
        assert resp.status_code == 404


class TestPresetImport:
    ST_JSON = {
        "prompts": [
            {"identifier": "main", "name": "Main", "content": "You are X", "enabled": True, "role": "system"},
            {"identifier": "chatHistory", "name": "History", "content": "", "injection_position": 1, "injection_depth": 3},
            {"identifier": "personaDescription", "name": "Persona", "content": "I am Y"},
        ],
        "prompt_order": [
            {"order": [{"identifier": "main", "enabled": True}, {"identifier": "chatHistory", "enabled": False}]},
        ],
    }

    async def test_import_sillytavern_json(self, client):
        resp = await client.post(
            "/api/presets/import",
            files={"file": ("my_preset.json", json.dumps(self.ST_JSON).encode(), "application/json")},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "my_preset"
        assert data["block_count"] == 3

        detail = await client.get(f"/api/presets/{data['id']}")
        blocks = detail.json()["blocks"]
        by_name = {b["name"]: b for b in blocks}
        assert by_name["Main"]["block_type"] == "text"
        assert by_name["History"]["block_type"] == "chat_history"
        assert by_name["History"]["injection_depth"] == 3
        assert by_name["Persona"]["block_type"] == "user_persona"
        assert by_name["History"]["enabled"] == 0, "prompt_order enabled=false must win"
        positions = [b["position"] for b in blocks]
        assert positions == sorted(positions)

    async def test_import_invalid_json_400(self, client):
        resp = await client.post(
            "/api/presets/import",
            files={"file": ("bad.json", b"{not json", "application/json")},
        )
        assert resp.status_code == 400
