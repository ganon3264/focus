"""Tests for POST /api/chats/{id}/summarize and the forked-chat context.

The summary turn is ephemeral: it must not touch the source chat's messages,
must store a ``chat_summaries`` row, and must create a child chat whose prompt
context carries the accumulated summary plus the parent's recent messages. The
endpoint streams SSE so provider failures retry like normal generation.
"""

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from io import BytesIO

import aiosqlite
import pytest
from PIL import Image

from focus.core.paths import ATTACHMENTS_DIR
from tests.helpers import create_character, create_chat, create_persona, create_preset


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _db_path(tmp_test_dir: str) -> str:
    return os.path.join(tmp_test_dir, "test.db")


async def _fetchall(db_path: str, sql: str, *params):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]


async def _insert_message(db_path, chat_id, role, position, content="") -> str:
    msg_id = str(uuid.uuid4())
    now = _now_iso()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, active_index, created_at)"
            " VALUES (?, ?, ?, ?, 0, ?)",
            (msg_id, chat_id, role, position, now),
        )
        await db.execute(
            "INSERT INTO message_variants (id, message_id, variant_index, content, created_at)"
            " VALUES (?, ?, 0, ?, ?)",
            (str(uuid.uuid4()), msg_id, content, now),
        )
        await db.commit()
    return msg_id


async def _insert_image_message(
    db_path, chat_id, role, position, filename, text="see this"
) -> str:
    msg_id = str(uuid.uuid4())
    variant_id = str(uuid.uuid4())
    now = _now_iso()
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    path = ATTACHMENTS_DIR / filename
    buf = BytesIO()
    Image.new("RGB", (4, 4), (255, 0, 0)).save(buf, format="PNG")
    path.write_bytes(buf.getvalue())
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, active_index, created_at)"
            " VALUES (?, ?, ?, ?, 0, ?)",
            (msg_id, chat_id, role, position, now),
        )
        await db.execute(
            "INSERT INTO message_variants (id, message_id, variant_index, content, created_at)"
            " VALUES (?, ?, 0, ?, ?)",
            (variant_id, msg_id, text, now),
        )
        await db.execute(
            "INSERT INTO message_attachments"
            " (id, chat_id, message_id, variant_id, file_path, mime_type, created_at)"
            " VALUES (?, ?, ?, ?, ?, 'image/png', ?)",
            (str(uuid.uuid4()), chat_id, msg_id, variant_id, str(path), now),
        )
        await db.commit()
    return msg_id


def _parse_sse(text: str) -> list[dict]:
    events: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        try:
            events.append(json.loads(line[6:].strip()))
        except json.JSONDecodeError:
            pass
    return events


def _done_id(events: list[dict]) -> str | None:
    done = [e for e in events if e.get("type") == "done"]
    return done[-1].get("id") if done else None


async def _summarize(client, chat_id, provider_id, message_id=""):
    resp = await client.post(
        f"/api/chats/{chat_id}/summarize",
        json={"provider_id": provider_id, "message_id": message_id},
    )
    return resp.status_code, _parse_sse(resp.text)


class FakeProvider:
    supports_prefill = True
    echoes_prefill = True
    supports_tools = True

    def __init__(self, text="A concise recap."):
        self.text = text
        self.calls = 0
        self.messages_seen: list[list[dict]] = []
        self.kwargs_seen: list[dict] = []

    async def stream_complete(self, messages, **kwargs):
        self.calls += 1
        self.messages_seen.append(messages)
        self.kwargs_seen.append(kwargs)
        yield {"type": "token", "text": self.text}
        yield {"type": "done"}

    async def supported_modalities(self, model):
        return None


class FlakyProvider(FakeProvider):
    """Fails with a retryable error for the first *failures* calls."""

    def __init__(self, failures=1, text="A concise recap."):
        super().__init__(text)
        self.failures = failures

    async def stream_complete(self, messages, **kwargs):
        self.calls += 1
        if self.calls <= self.failures:
            err = RuntimeError("upstream exploded")
            err.status_code = 500
            raise err
        yield {"type": "token", "text": self.text}
        yield {"type": "done"}


class SlowProvider(FakeProvider):
    """Parks the provider call forever — used to exercise the stop path."""

    def __init__(self):
        super().__init__("never")
        self.started = asyncio.Event()

    async def stream_complete(self, messages, **kwargs):
        self.calls += 1
        self.messages_seen.append(messages)
        self.started.set()
        await asyncio.Event().wait()  # parked until the call is cancelled
        yield {"type": "done"}  # unreachable; the yield makes this an async generator


@pytest.fixture
def patch_provider(monkeypatch):
    def _patch(provider):
        import focus.providers as providers_mod
        from focus.routers import stream as stream_module

        monkeypatch.setattr(providers_mod, "create_provider", lambda row: provider)
        monkeypatch.setattr(stream_module, "create_provider", lambda row: provider)

    return _patch


async def _create_provider(client, name="TestProvider", model="gpt-4", config=None):
    body = {"name": name, "type": "openai_compat", "model": model}
    if config is not None:
        body["config"] = config
    resp = await client.post("/api/providers/", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _setup(client, *, title="Chat"):
    char = await create_character(client, "Char")
    persona = await create_persona(client, "P")
    preset = await create_preset(client, "Pr")
    chat = await create_chat(client, char["id"], persona["id"], preset["id"], title=title)
    return chat, await _create_provider(client)


async def _itemize(client, chat_id) -> dict:
    resp = await client.post(
        "/api/itemize",
        json={"chat_id": chat_id, "user_message": "", "attachment_ids": [], "regenerate": False},
    )
    assert resp.status_code == 200
    return resp.json()


async def _itemize_text(client, chat_id) -> str:
    data = await _itemize(client, chat_id)
    parts: list[str] = []
    for msg in data["messages"]:
        for part in msg["parts"]:
            parts.append(part.get("text") or "")
    return "\n".join(parts)


class TestSummarize:
    async def test_fork_stores_summary_without_touching_parent(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, prov_id = await _setup(client)
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hi!")
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "user", 1, "Hello there")
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 2, "Greetings")

        fake = FakeProvider("They greeted each other.")
        patch_provider(fake)

        status, events = await _summarize(client, chat["id"], prov_id)
        assert status == 200
        child_id = _done_id(events)
        assert child_id and child_id != chat["id"]
        assert fake.calls == 1

        # Parent messages are untouched; the ephemeral turn was never persisted.
        parent_rows = await _fetchall(
            _db_path(tmp_test_dir),
            "SELECT role, position FROM messages WHERE chat_id = ? ORDER BY position",
            chat["id"],
        )
        assert len(parent_rows) == 3

        child = (await _fetchall(
            _db_path(tmp_test_dir), "SELECT * FROM chats WHERE id = ?", child_id,
        ))[0]
        assert child["parent_chat_id"] == chat["id"]
        assert child["summary_id"]

        summaries = await _fetchall(
            _db_path(tmp_test_dir),
            "SELECT * FROM chat_summaries WHERE chat_id = ?", chat["id"],
        )
        assert len(summaries) == 1
        assert summaries[0]["content"] == "They greeted each other."

        # The child's assembled context carries the summary and the parent window.
        text = await _itemize_text(client, child_id)
        assert "They greeted each other." in text
        assert "Greetings" in text

    async def test_resummarize_accumulates_chunks(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, prov_id = await _setup(client)
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hi!")

        fake = FakeProvider("Chunk one.")
        patch_provider(fake)
        _, events = await _summarize(client, chat["id"], prov_id)
        child_id = _done_id(events)

        fake.text = "Chunk two."
        _, events = await _summarize(client, child_id, prov_id)
        grandchild_id = _done_id(events)

        text = await _itemize_text(client, grandchild_id)
        assert "[Summary 1]\nChunk one." in text
        assert "[Summary 2]\nChunk two." in text

    async def test_missing_provider_is_rejected(self, client):
        char = await create_character(client, "Char")
        chat = await create_chat(client, char["id"])
        status, events = await _summarize(client, chat["id"], "")
        assert status == 400
        assert events == []

    async def test_summarize_from_message_cuts_at_that_point(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, prov_id = await _setup(client)
        db_path = _db_path(tmp_test_dir)
        await _insert_message(db_path, chat["id"], "assistant", 0, "Hi!")
        await _insert_message(db_path, chat["id"], "user", 1, "First")
        cut_msg = await _insert_message(db_path, chat["id"], "assistant", 2, "Middle")
        await _insert_message(db_path, chat["id"], "user", 3, "Later")

        patch_provider(FakeProvider("Recap."))

        status, events = await _summarize(client, chat["id"], prov_id, message_id=cut_msg)
        assert status == 200
        child_id = _done_id(events)

        summary = (await _fetchall(
            db_path, "SELECT * FROM chat_summaries WHERE chat_id = ?", chat["id"],
        ))[0]
        assert summary["covered_to_position"] == 2

        # The child inherits only up to the cut; later parent turns are excluded.
        text = await _itemize_text(client, child_id)
        assert "Recap." in text
        assert "Middle" in text
        assert "Later" not in text

    async def test_child_partial_renders_lineage_with_marker(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, prov_id = await _setup(client)
        db_path = _db_path(tmp_test_dir)
        await _insert_message(db_path, chat["id"], "assistant", 0, "Hi!")
        await _insert_message(db_path, chat["id"], "user", 1, "Inherited turn")

        patch_provider(FakeProvider("Recap."))
        _, events = await _summarize(client, chat["id"], prov_id)
        child_id = _done_id(events)

        resp = await client.get(f"/partials/message-list/{child_id}")
        assert resp.status_code == 200
        assert "Inherited turn" in resp.text
        assert "message-ancestor" in resp.text
        assert "summary-boundary-btn" in resp.text

    async def test_summary_block_carries_settings(
        self, client, tmp_test_dir, patch_provider
    ):
        char = await create_character(client, "Char")
        persona = await create_persona(client, "P")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], persona["id"], preset["id"])
        prov_a = await _create_provider(client, name="A", model="gpt-4")
        prov_b = await _create_provider(client, name="B", model="gpt-5")

        block = await client.put(f"/api/presets/{preset['id']}/settings", json={"summary": {
            "instruction": "Custom instruction.",
            "keep": 1,
            "provider_id": prov_b,
        }})
        assert block.status_code == 200, block.text

        db_path = _db_path(tmp_test_dir)
        await _insert_message(db_path, chat["id"], "assistant", 0, "Greeting")
        await _insert_message(db_path, chat["id"], "user", 1, "Older")
        await _insert_message(db_path, chat["id"], "assistant", 2, "Newest")

        patch_provider(FakeProvider("Recap."))
        status, events = await _summarize(client, chat["id"], prov_a)
        assert status == 200
        child_id = _done_id(events)

        # The block's provider override was used, not the request's.
        summary = (await _fetchall(
            db_path, "SELECT * FROM chat_summaries WHERE chat_id = ?", chat["id"],
        ))[0]
        assert summary["model_name"] == "gpt-5"

        data = await _itemize(client, child_id)
        text = "\n".join(p.get("text") or "" for m in data["messages"] for p in m["parts"])
        assert "Recap." in text
        assert "Newest" in text
        assert "Older" not in text          # keep=1 window
        assert "Greeting" not in text

        recap = [m for m in data["messages"] if any(
            "Recap." in (p.get("text") or "") for p in m["parts"]
        )]
        assert recap and recap[0]["role"] == "system"

    async def test_window_media_survives_into_fork(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, prov_id = await _setup(client)
        db_path = _db_path(tmp_test_dir)
        await _insert_message(db_path, chat["id"], "assistant", 0, "Hi!")
        await _insert_image_message(db_path, chat["id"], "user", 1, "window-media.png")

        patch_provider(FakeProvider("Recap."))
        _, events = await _summarize(client, chat["id"], prov_id)
        child_id = _done_id(events)

        # The image is interleaved via {{media:N}} rather than dropped to text.
        data = await _itemize(client, child_id)
        assert any(
            p.get("type") == "image" for m in data["messages"] for p in m["parts"]
        )

    async def test_media_messages_section_pulls_old_media(
        self, client, tmp_test_dir, patch_provider
    ):
        char = await create_character(client, "Char")
        persona = await create_persona(client, "P")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], persona["id"], preset["id"])
        prov = await _create_provider(client)
        await client.put(f"/api/presets/{preset['id']}/settings", json={
            "summary": {"keep": 2},
        })

        db_path = _db_path(tmp_test_dir)
        await _insert_message(db_path, chat["id"], "assistant", 0, "Old intro")
        await _insert_image_message(db_path, chat["id"], "user", 1, "old-media.png", text="old photo")
        await _insert_message(db_path, chat["id"], "assistant", 2, "Middle")
        await _insert_image_message(db_path, chat["id"], "user", 3, "recent-media.png", text="recent photo")
        await _insert_message(db_path, chat["id"], "assistant", 4, "Latest")

        patch_provider(FakeProvider("Recap."))
        _, events = await _summarize(client, chat["id"], prov)
        child_id = _done_id(events)

        data = await _itemize(client, child_id)
        flat = [p for m in data["messages"] for p in m["parts"]]
        full = "\n".join(p.get("text") or "" for p in flat)
        assert "<summary>" in full and "Recap." in full
        assert "old photo" in full and "recent photo" in full
        # Older non-media turns are covered by the summary, not repeated.
        assert "Old intro" not in full

        img_idx = [i for i, p in enumerate(flat) if p.get("type") == "image"]
        assert len(img_idx) == 2
        assert "<media_messages>" in (flat[img_idx[0] - 1].get("text") or "")
        assert "<last_messages>" in (flat[img_idx[1] - 1].get("text") or "")

    async def test_disabled_summary_block_rejects_summarize(self, client):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        prov = await _create_provider(client, name="A")
        block_id = (await client.post(f"/api/presets/{preset['id']}/blocks", json={
            "name": "Summary", "block_type": "summary",
        })).json()["id"]
        await client.patch(
            f"/api/presets/{preset['id']}/blocks/{block_id}", json={"enabled": False},
        )
        status, _ = await _summarize(client, chat["id"], prov)
        assert status == 400

    async def test_arranger_renders_summary_settings(self, client):
        preset = await create_preset(client, "Pr")
        await client.put(f"/api/presets/{preset['id']}/settings", json={
            "summary": {"keep": 5, "provider_id": ""},
        })

        resp = await client.get(f"/partials/prompt-arranger/{preset['id']}")
        assert resp.status_code == 200
        assert "Summary" in resp.text
        assert "Keep messages" in resp.text
        assert "Same as chat" in resp.text
        # The default prompt is prefilled, not hidden behind "empty".
        assert "Summarize the conversation so far" in resp.text

    async def test_post_history_blocks_excluded_from_summarize(
        self, client, tmp_test_dir, patch_provider
    ):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        prov = await _create_provider(client)
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hi!")

        # Appended after Chat History, so it lands in the post-history section.
        await client.post(f"/api/presets/{preset['id']}/blocks", json={
            "name": "Style", "block_type": "text", "content": "POST HISTORY MARKER",
        })

        # It is part of the normal prompt...
        assert "POST HISTORY MARKER" in await _itemize_text(client, chat["id"])

        # ...but not of the summarization pass.
        fake = FakeProvider("Recap.")
        patch_provider(fake)
        await _summarize(client, chat["id"], prov)
        summary_input = str(fake.messages_seen[0])
        assert "POST HISTORY MARKER" not in summary_input

    async def test_summary_chunks_can_be_edited(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, prov_id = await _setup(client)
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hi!")
        patch_provider(FakeProvider("Original summary."))
        _, events = await _summarize(client, chat["id"], prov_id)
        child_id = _done_id(events)

        resp = await client.get(f"/api/chats/{child_id}/summary")
        assert resp.status_code == 200
        chunks = resp.json()["chunks"]
        assert len(chunks) == 1
        assert chunks[0]["content"] == "Original summary."

        resp = await client.put(f"/api/chats/{child_id}/summary", json={
            "chunks": [{"id": chunks[0]["id"], "content": "Edited summary."}],
        })
        assert resp.status_code == 200, resp.text

        text = await _itemize_text(client, child_id)
        assert "Edited summary." in text
        assert "Original summary." not in text

    async def test_editing_foreign_summary_chunk_is_rejected(self, client, patch_provider):
        chat, prov_id = await _setup(client)
        patch_provider(FakeProvider("Recap."))
        await _summarize(client, chat["id"], prov_id)
        resp = await client.put(f"/api/chats/{chat['id']}/summary", json={
            "chunks": [{"id": "does-not-exist", "content": "x"}],
        })
        assert resp.status_code == 404

    async def test_transient_failure_retries_then_succeeds(
        self, client, tmp_test_dir, patch_provider
    ):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        prov = await _create_provider(client, config={
            "retry": {"enabled": True, "base_delay": 0, "max_delay": 0, "max_retries": 3},
        })
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hi!")

        fake = FlakyProvider(failures=1, text="Recovered summary.")
        patch_provider(fake)

        status, events = await _summarize(client, chat["id"], prov)
        assert status == 200
        assert fake.calls == 2
        retries = [e for e in events if e.get("type") == "retry"]
        assert retries and retries[0]["attempt"] == 1
        assert _done_id(events)

        summary = (await _fetchall(
            _db_path(tmp_test_dir),
            "SELECT content FROM chat_summaries WHERE chat_id = ?", chat["id"],
        ))[0]
        assert summary["content"] == "Recovered summary."

    async def test_preset_macro_block_controls_structure(
        self, client, tmp_test_dir, patch_provider
    ):
        char = await create_character(client, "Char")
        persona = await create_persona(client, "P")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], persona["id"], preset["id"])
        prov = await _create_provider(client)
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hi!")

        await client.post(f"/api/presets/{preset['id']}/blocks", json={
            "name": "Summary", "block_type": "summary", "role": "user",
            "content": "CUSTOM BEGIN {{summary}} CUSTOM END",
        })

        patch_provider(FakeProvider("Recap."))
        status, events = await _summarize(client, chat["id"], prov)
        assert status == 200
        child_id = _done_id(events)

        data = await _itemize(client, child_id)
        text = "\n".join(p.get("text") or "" for m in data["messages"] for p in m["parts"])
        assert "CUSTOM BEGIN" in text
        assert "[Summary 1]\nRecap." in text
        assert "CUSTOM END" in text
        # The macro block owns the structure; the default wrapper must not run.
        assert "<summary>" not in text
        assert text.count("Recap.") == 1
        recap = [m for m in data["messages"] if any(
            "Recap." in (p.get("text") or "") for p in m["parts"]
        )]
        assert recap and recap[0]["role"] == "user"

    async def test_summary_block_omitted_without_summary(self, client):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        await client.post(f"/api/presets/{preset['id']}/blocks", json={
            "name": "Summary", "block_type": "summary", "role": "user",
            "content": "CUSTOM BEGIN {{summary}} CUSTOM END",
        })

        text = await _itemize_text(client, chat["id"])
        assert "CUSTOM BEGIN" not in text
        assert "<summary>" not in text

    async def test_summary_macro_in_text_block_without_summary_is_stripped(self, client):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        await client.post(f"/api/presets/{preset['id']}/blocks", json={
            "name": "Note", "block_type": "text", "role": "system",
            "content": "BEGIN {{summary}} END",
        })

        # A non-summarized chat has no section to splice, so the macro resolves
        # to nothing rather than leaking the internal placeholder token.
        text = await _itemize_text(client, chat["id"])
        assert "BEGIN" in text and "END" in text
        assert "\x00" not in text
        assert "section:" not in text

    async def test_summary_macro_in_message_text_is_stripped(self, client, tmp_test_dir):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        await _insert_message(
            _db_path(tmp_test_dir), chat["id"], "user", 0, "BEGIN {{summary}} END",
        )

        # Message text is macro-expanded like block text and must never leak
        # the internal section token into the prompt.
        text = await _itemize_text(client, chat["id"])
        assert "BEGIN" in text and "END" in text
        assert "\x00" not in text

    async def test_summary_macro_in_message_text_splices_summary_in_fork(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, prov_id = await _setup(client)
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hi!")
        patch_provider(FakeProvider("The recap."))
        _, events = await _summarize(client, chat["id"], prov_id)
        child_id = _done_id(events)
        await _insert_message(
            _db_path(tmp_test_dir), child_id, "user", 0, "Recap: {{summary}}",
        )

        # In a fork the macro splices the accumulated summary, like in blocks.
        text = await _itemize_text(client, child_id)
        assert "Recap: " in text
        assert "The recap." in text
        assert "\x00" not in text

    async def test_preset_settings_roundtrip(self, client):
        preset = await create_preset(client, "Pr")
        resp = await client.get(f"/api/presets/{preset['id']}/settings")
        assert resp.status_code == 200
        assert resp.json()["summary"]["active"] is True
        assert resp.json()["summary"]["keep"] == 20
        assert resp.json()["summary"]["max_tokens"] == 8192

        resp = await client.put(f"/api/presets/{preset['id']}/settings", json={
            "summary": {"enabled": False, "keep": 7, "max_tokens": 500, "provider_id": "abc"},
        })
        assert resp.status_code == 200

        body = (await client.get(f"/api/presets/{preset['id']}/settings")).json()["summary"]
        assert body["active"] is False
        assert body["keep"] == 7
        assert body["max_tokens"] == 500
        assert body["provider_id"] == "abc"

        # A disabled Summary block also resolves active=False.
        await client.put(f"/api/presets/{preset['id']}/settings", json={
            "summary": {"enabled": True},
        })
        await client.post(f"/api/presets/{preset['id']}/blocks", json={
            "name": "Summary", "block_type": "summary", "role": "system",
            "content": "{{summary}}", "enabled": False,
        })
        body = (await client.get(f"/api/presets/{preset['id']}/settings")).json()["summary"]
        assert body["active"] is False

        assert (await client.get("/api/presets/nope/settings")).status_code == 404

    async def test_permanent_failure_creates_nothing(
        self, client, tmp_test_dir, patch_provider
    ):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        prov = await _create_provider(client, config={"retry": {"enabled": False}})
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hi!")

        patch_provider(FlakyProvider(failures=99))

        status, events = await _summarize(client, chat["id"], prov)
        assert status == 200
        assert any(e.get("type") == "error" for e in events)
        assert _done_id(events) is None

        assert await _fetchall(
            _db_path(tmp_test_dir),
            "SELECT * FROM chat_summaries WHERE chat_id = ?", chat["id"],
        ) == []
        children = await _fetchall(
            _db_path(tmp_test_dir),
            "SELECT id FROM chats WHERE parent_chat_id = ?", chat["id"],
        )
        assert children == []


class TestSummaryPins:
    """Pinned turns ride verbatim into forks via {{summary_pins}}."""

    async def _fork_with_pins(self, client, tmp_test_dir, patch_provider, keep=None):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        if keep is not None:
            await client.put(
                f"/api/presets/{preset['id']}/settings", json={"summary": {"keep": keep}},
            )
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        setup = await _insert_message(
            _db_path(tmp_test_dir), chat["id"], "user", 0, "SETUP RULES XYZ",
        )
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 1, "ok")
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "user", 2, "UNPINNED FLUFF")
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 3, "later")

        resp = await client.put(
            f"/api/chats/{chat['id']}/messages/{setup}/pin", json={"pinned": True},
        )
        assert resp.status_code == 200 and resp.json()["pinned"] is True
        return chat, setup

    async def test_pinned_message_survives_compaction(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, _ = await self._fork_with_pins(client, tmp_test_dir, patch_provider, keep=1)
        prov = await _create_provider(client)
        patch_provider(FakeProvider("Recap."))
        _, events = await _summarize(client, chat["id"], prov)
        child_id = _done_id(events)

        # Pinned and outside the live window: carried verbatim. Unpinned and
        # outside: compressed away with the summary.
        text = await _itemize_text(client, child_id)
        assert "SETUP RULES XYZ" in text
        assert "UNPINNED FLUFF" not in text

    async def test_summary_pins_macro_splices_in_block(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, _ = await self._fork_with_pins(client, tmp_test_dir, patch_provider, keep=1)
        preset_id = (await _fetchall(
            _db_path(tmp_test_dir), "SELECT preset_id FROM chats WHERE id = ?", chat["id"],
        ))[0]["preset_id"]
        await client.post(f"/api/presets/{preset_id}/blocks", json={
            "name": "Pins", "block_type": "text", "role": "system",
            "content": "PINS[{{summary_pins}}]",
        })
        prov = await _create_provider(client)
        patch_provider(FakeProvider("Recap."))
        _, events = await _summarize(client, chat["id"], prov)
        child_id = _done_id(events)

        text = await _itemize_text(client, child_id)
        assert "PINS[user: SETUP RULES XYZ]" in text

    async def test_pinned_message_inside_window_is_not_duplicated(
        self, client, tmp_test_dir, patch_provider
    ):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        msg_id = await _insert_message(
            _db_path(tmp_test_dir), chat["id"], "user", 0, "PINNED MARKER ONE",
        )
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 1, "ok")
        await client.put(
            f"/api/chats/{chat['id']}/messages/{msg_id}/pin", json={"pinned": True},
        )

        prov = await _create_provider(client)
        patch_provider(FakeProvider("Recap."))
        _, events = await _summarize(client, chat["id"], prov)
        child_id = _done_id(events)

        # Default keep (20) leaves everything in the live window, so the pin
        # must not be repeated by {{summary_pins}}.
        text = await _itemize_text(client, child_id)
        assert text.count("PINNED MARKER ONE") == 1

    async def test_pins_survive_repeated_compaction(
        self, client, tmp_test_dir, patch_provider
    ):
        chat, _ = await self._fork_with_pins(client, tmp_test_dir, patch_provider, keep=1)
        prov = await _create_provider(client)
        patch_provider(FakeProvider("Recap."))
        _, events = await _summarize(client, chat["id"], prov)
        child_id = _done_id(events)

        await _insert_message(_db_path(tmp_test_dir), child_id, "assistant", 0, "b1")
        _, events = await _summarize(client, child_id, prov)
        grandchild_id = _done_id(events)

        # The root's pin is two chain chunks deep and must still be verbatim.
        text = await _itemize_text(client, grandchild_id)
        assert "SETUP RULES XYZ" in text


class TestSummarizeWireHygiene:
    async def test_no_assembly_markers_reach_the_provider(self, client, tmp_test_dir, patch_provider):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        db_path = _db_path(tmp_test_dir)
        asst_id = await _insert_message(db_path, chat["id"], "assistant", 0, "Hi!")

        # A tool round whose extra payload is a synthetic internal user
        # message — the summarize path must scrub it like the generation one.
        async with aiosqlite.connect(db_path) as conn:
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.execute(
                "INSERT INTO tool_calls"
                " (id, chat_id, message_id, variant_id, tool_name, arguments, result, extra_message_json, created_at)"
                " VALUES (?, ?, ?,"
                " (SELECT id FROM message_variants WHERE message_id = ? LIMIT 1),"
                " ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), chat["id"], asst_id, asst_id,
                 "look", "{}", "ok",
                 json.dumps({"role": "user", "content": "INTERNAL EXTRA", "internal": True}),
                 _now_iso()),
            )
            await conn.commit()

        prov = await _create_provider(client)
        fake = FakeProvider("Recap.")
        patch_provider(fake)
        status, events = await _summarize(client, chat["id"], prov)
        assert status == 200 and _done_id(events)

        seen = fake.messages_seen[0]
        assert any("INTERNAL EXTRA" in str(m.get("content")) for m in seen)
        for msg in seen:
            assert "internal" not in msg
            assert not any(k.startswith("_") for k in msg)


class TestSummaryMaxTokens:
    async def test_max_tokens_setting_reaches_the_provider(self, client, tmp_test_dir, patch_provider):
        char = await create_character(client, "Char")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], preset_id=preset["id"])
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hi!")
        prov = await _create_provider(client)

        fake = FakeProvider("Recap.")
        patch_provider(fake)

        await client.put(f"/api/presets/{preset['id']}/settings", json={
            "summary": {"max_tokens": 123},
        })
        status, events = await _summarize(client, chat["id"], prov)
        assert status == 200 and _done_id(events)
        assert fake.kwargs_seen[-1]["max_tokens"] == 123

        # 0 = no explicit cap: provider params / adapter default apply.
        await client.put(f"/api/presets/{preset['id']}/settings", json={
            "summary": {"max_tokens": 0},
        })
        status, events = await _summarize(client, chat["id"], prov)
        assert status == 200 and _done_id(events)
        assert "max_tokens" not in fake.kwargs_seen[-1]


class TestSummaryCancel:
    async def test_running_summary_can_be_cancelled(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        await _insert_message(_db_path(tmp_test_dir), chat["id"], "assistant", 0, "Hi!")
        fake = SlowProvider()
        patch_provider(fake)

        task = asyncio.create_task(_summarize(client, chat["id"], prov_id))
        await asyncio.wait_for(fake.started.wait(), timeout=5)

        resp = await client.post(f"/api/chats/{chat['id']}/summarize/stop")
        assert resp.status_code == 200

        status, events = await asyncio.wait_for(task, timeout=5)
        assert status == 200
        assert events[-1] == {"type": "done", "cancelled": True}

        # Cancellation persists nothing and releases the run slot.
        assert await _fetchall(_db_path(tmp_test_dir), "SELECT * FROM chat_summaries") == []
        assert await _fetchall(
            _db_path(tmp_test_dir),
            "SELECT id FROM chats WHERE parent_chat_id = ?", chat["id"],
        ) == []
        assert (await client.post(f"/api/chats/{chat['id']}/summarize/stop")).status_code == 404

    async def test_stop_without_active_summary_is_404(self, client):
        chat = await create_chat(client)
        assert (await client.post(f"/api/chats/{chat['id']}/summarize/stop")).status_code == 404
