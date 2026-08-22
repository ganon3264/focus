"""Happy-path tests for the /api/stream generation endpoint.

Uses a fake provider (injected via ``focus.routers.stream.create_provider``)
to exercise the real generation loop end-to-end: SSE streaming, meta/reasoning
accumulation, tool iteration with real builtin tools, graceful stop,
non-stream mode, and the continue/prefill path.

The DB assertions use the same raw aiosqlite helpers as test_stream_abort.py.
"""

import asyncio
import json
import os
import time
import uuid
from datetime import UTC, datetime
from io import BytesIO

import aiosqlite
import pytest
from PIL import Image

from focus.tools import ToolCall
from tests.helpers import create_character, create_chat, create_persona, create_preset


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _db_path(tmp_test_dir: str) -> str:
    return os.path.join(tmp_test_dir, "test.db")


async def _consume_sse_events(resp) -> list[dict]:
    """Consume an SSE response and return the list of parsed event payloads."""
    events: list[dict] = []
    for line in resp.text.splitlines():
        line = line.strip()
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if not payload:
            continue
        try:
            events.append(json.loads(payload))
        except json.JSONDecodeError:
            pass
    return events


async def _fetchone(db_path: str, sql: str, *params):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        return await cur.fetchone()


async def _fetchall(db_path: str, sql: str, *params):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        return await cur.fetchall()


async def _assistant_variant(db_path: str, chat_id: str) -> dict | None:
    row = await _fetchone(
        db_path,
        "SELECT m.id as msg_id, mv.variant_index, mv.content, mv.variant_meta, mv.segments_json, mv.model_name "
        "FROM messages m JOIN message_variants mv ON mv.message_id = m.id "
        "WHERE m.chat_id = ? AND m.role = 'assistant' AND m.position > 0 ORDER BY m.position LIMIT 1",
        chat_id,
    )
    return dict(row) if row else None


class FakeProvider:
    """Provider that replays a scripted list of event rounds.

    Each round is either a list of events to yield or an Exception to raise
    when that round is reached. The number of ``stream_complete`` calls is
    recorded so tests can assert the tool-iteration loop actually re-invoked
    the provider.
    """

    supports_prefill = True
    echoes_prefill = True
    supports_tools = True

    def __init__(
        self,
        rounds,
        *,
        echoes_prefill=True,
        supports_prefill=True,
        supports_tools=True,
    ):
        self.rounds = list(rounds)
        self.echoes_prefill = echoes_prefill
        self.supports_prefill = supports_prefill
        self.supports_tools = supports_tools
        self.calls = 0
        self.all_kwargs: list[dict] = []

    async def stream_complete(self, messages, **kwargs):
        self.calls += 1
        self.all_kwargs.append(kwargs)
        if self.calls > len(self.rounds):
            yield {"type": "done"}
            return
        events = self.rounds[self.calls - 1]
        if isinstance(events, BaseException):
            raise events
        for e in events:
            yield e


@pytest.fixture
def patch_provider(monkeypatch):
    """Redirect provider construction to a fake for the duration of a test."""

    def _patch(provider: FakeProvider):
        import focus.providers as providers_mod
        from focus.routers import stream as stream_module

        monkeypatch.setattr(providers_mod, "create_provider", lambda row: provider)
        monkeypatch.setattr(stream_module, "create_provider", lambda row: provider)

    return _patch


async def _setup(client, *, title="Chat"):
    """Create character/persona/preset/chat + a provider row; return (chat, provider_id)."""
    char = await create_character(client, "Char")
    persona = await create_persona(client, "P")
    preset = await create_preset(client, "Pr")
    chat = await create_chat(client, char["id"], persona["id"], preset["id"], title=title)
    resp = await client.post(
        "/api/providers/",
        json={"name": "TestProvider", "type": "openai_compat", "model": "gpt-4"},
    )
    assert resp.status_code == 201
    return chat, resp.json()["id"]


async def _stream(client, chat_id, provider_id, **overrides):
    body = {
        "chat_id": chat_id,
        "provider_id": provider_id,
        "user_message": "Hello",
        "samplers": {"stream_enabled": True},
        "regenerate": False,
        "attachment_ids": [],
        "tools_enabled": False,
        "tool_read_only": True,
    }
    body.update(overrides)
    return await client.post("/api/stream", json=body)


class TestStreamingGeneration:
    async def test_tokens_and_usage_persisted(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        fake = FakeProvider([
            [
                {"type": "token", "text": "Hello"},
                {"type": "token", "text": " world"},
                {"type": "usage", "usage": {
                    "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                    "cached_tokens": 0, "reasoning_tokens": 0,
                }},
                {"type": "done"},
            ],
        ])
        patch_provider(fake)

        resp = await _stream(client, chat["id"], prov_id)
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")

        events = await _consume_sse_events(resp)
        assert events[0]["type"] == "start"
        assert events[0]["message_id"] is not None
        assert events[0]["user_message_id"] is not None
        tokens = [e["text"] for e in events if e.get("type") == "token"]
        assert tokens == ["Hello", " world"]
        done = [e for e in events if e.get("type") == "done"]
        assert done and done[0]["message_id"] == events[0]["message_id"]

        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        assert asst["content"] == "Hello world"
        assert asst["model_name"] == "gpt-4"
        assert asst["variant_meta"] is None
        segments = json.loads(asst["segments_json"])
        assert [s["type"] for s in segments] == ["text"]

        user = await _fetchone(
            _db_path(tmp_test_dir),
            "SELECT mv.content FROM messages m JOIN message_variants mv ON mv.message_id = m.id "
            "WHERE m.chat_id = ? AND m.role = 'user'",
            chat["id"],
        )
        assert user[0] == "Hello"

        usage = await _fetchone(
            _db_path(tmp_test_dir),
            "SELECT total_tokens, prompt_tokens, completion_tokens, provider_type, model_name, message_id "
            "FROM generation_usage WHERE chat_id = ?",
            chat["id"],
        )
        assert usage[0] == 15 and usage[1] == 10 and usage[2] == 5
        assert usage[3] == "openai_compat" and usage[4] == "gpt-4"
        assert usage[5] == events[0]["message_id"]

    async def test_midstream_checkpoint_saves_variant(self, client, tmp_test_dir, patch_provider):
        """Multi-token streams must produce a correct final save (no checkpoint corruption)."""
        chat, prov_id = await _setup(client)
        fake = FakeProvider([
            [{"type": "token", "text": f"w{i}"} for i in range(7)] + [{"type": "done"}],
        ])
        patch_provider(fake)

        resp = await _stream(client, chat["id"], prov_id)
        events = await _consume_sse_events(resp)
        assert len([e for e in events if e.get("type") == "token"]) == 7

        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        assert asst["content"] == "".join(f"w{i}" for i in range(7))

    async def test_timed_midstream_checkpoint(self, client, tmp_test_dir, patch_provider, monkeypatch):
        """With the checkpoint interval at zero, partial text must hit the DB
        while the generation is still in flight (wall-clock driven)."""
        from focus.routers import stream as stream_module
        monkeypatch.setattr(stream_module, "_CHECKPOINT_INTERVAL_SECS", 0)

        chat, prov_id = await _setup(client)
        release = asyncio.Event()

        class GatedProvider(FakeProvider):
            async def stream_complete(self, messages, **kwargs):
                yield {"type": "token", "text": "partial-"}
                await release.wait()
                yield {"type": "done"}

        fake = GatedProvider([])
        patch_provider(fake)

        db_path = _db_path(tmp_test_dir)
        task = asyncio.create_task(_stream(client, chat["id"], prov_id))
        deadline = time.monotonic() + 5
        content = None
        while time.monotonic() < deadline:
            row = await _fetchone(
                db_path,
                "SELECT mv.content FROM messages m JOIN message_variants mv ON mv.message_id = m.id "
                "WHERE m.chat_id = ? AND m.role = 'assistant' AND m.position > 0",
                chat["id"],
            )
            if row:
                content = row[0]
                break
            await asyncio.sleep(0.01)
        assert content == "partial-", "timed checkpoint must persist partial text mid-stream"

        release.set()
        await asyncio.wait_for(task, 10)
        asst = await _assistant_variant(db_path, chat["id"])
        assert asst["content"] == "partial-"

    async def test_meta_reasoning_persisted(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        fake = FakeProvider([
            [
                {"type": "meta", "field": "reasoning", "value": "thinking "},
                {"type": "meta", "field": "reasoning", "value": "more"},
                {"type": "meta", "field": "reasoning_details", "value": [
                    {"id": "d1", "index": 0, "text": "detail-a", "format": "openai-responses-v1"},
                    {"id": "d2", "index": 1, "text": "detail-b", "format": "openai-responses-v1"},
                ]},
                {"type": "token", "text": "Answer"},
                {"type": "done"},
            ],
        ])
        patch_provider(fake)

        resp = await _stream(client, chat["id"], prov_id)
        events = await _consume_sse_events(resp)
        reasoning_events = [e["text"] for e in events if e.get("type") == "meta" and e.get("field") == "reasoning"]
        assert reasoning_events == ["thinking ", "more"]

        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        meta = json.loads(asst["variant_meta"])
        assert meta["reasoning"] == "thinking more"
        assert [d["id"] for d in meta["reasoning_details"]] == ["d1", "d2"]

        segments = json.loads(asst["segments_json"])
        assert [s["type"] for s in segments] == ["reasoning", "text"]

    async def test_tool_loop_executes_builtin_tool(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        target = os.path.join(tmp_test_dir, "notes.txt")
        with open(target, "w") as f:
            f.write("line1\nline2\nline3\n")

        await client.put(
            f"/api/chats/{chat['id']}/tool-states", json={"read_file": True}
        )

        fake = FakeProvider([
            [
                {"type": "token", "text": "Checking "},
                {"type": "tool_calls", "calls": [
                    ToolCall(id="call_1", name="read_file", arguments={"path": target, "lines": 2}),
                ]},
            ],
            [{"type": "token", "text": "done"}, {"type": "usage", "usage": {
                "prompt_tokens": 20, "completion_tokens": 3, "total_tokens": 23,
            }}, {"type": "done"}],
        ])
        patch_provider(fake)

        resp = await _stream(
            client, chat["id"], prov_id,
            user_message="read the file", tools_enabled=True, tool_read_only=True,
        )
        assert resp.status_code == 200
        events = await _consume_sse_events(resp)

        assert fake.calls == 2, "provider must be re-invoked after the tool round"
        assert "tools" in fake.all_kwargs[0]
        assert fake.all_kwargs[0]["tool_choice"] == "auto"

        calls = [e for e in events if e.get("type") == "tool_calls"]
        assert len(calls) == 1
        assert calls[0]["calls"][0]["id"] == "call_1"
        assert calls[0]["calls"][0]["name"] == "read_file"

        results = [e for e in events if e.get("type") == "tool_result"]
        assert len(results) == 1
        assert results[0]["call_id"] == "call_1"
        assert results[0]["name"] == "read_file"
        assert results[0]["is_error"] is False
        assert "line1" in results[0]["result"]

        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        assert asst["content"] == "Checking done"
        segments = json.loads(asst["segments_json"])
        types = [s["type"] for s in segments]
        assert types == ["text", "tool_boundary", "text"]
        boundary = segments[1]
        assert boundary["tool_calls"][0]["id"] == "call_1"

        tc_row = await _fetchone(
            _db_path(tmp_test_dir),
            "SELECT tool_name, arguments, result, is_error FROM tool_calls WHERE chat_id = ?",
            chat["id"],
        )
        assert tc_row[0] == "read_file"
        assert json.loads(tc_row[1]) == {"path": target, "lines": 2}
        assert tc_row[3] == 0

        history_resp = await client.get(f"/api/chats/{chat['id']}")
        assert history_resp.status_code == 200
        msgs = history_resp.json()["messages"]
        assert any(m["role"] == "assistant" for m in msgs)

    async def test_unknown_tool_returns_error_result(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        fake = FakeProvider([
            [{"type": "tool_calls", "calls": [
                ToolCall(id="c1", name="no_such_tool", arguments={}),
            ]}],
            [{"type": "token", "text": "recovered"}, {"type": "done"}],
        ])
        patch_provider(fake)

        resp = await _stream(
            client, chat["id"], prov_id,
            tools_enabled=True, tool_read_only=False,
        )
        events = await _consume_sse_events(resp)
        results = [e for e in events if e.get("type") == "tool_result"]
        assert len(results) == 1
        assert results[0]["is_error"] is True
        assert "unknown tool: no_such_tool" in results[0]["result"]
        assert fake.calls == 2

    async def test_read_only_blocks_writes_tool(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        await client.put(
            f"/api/chats/{chat['id']}/tool-states", json={"execute_shell": True}
        )
        fake = FakeProvider([
            [{"type": "tool_calls", "calls": [
                ToolCall(id="c1", name="execute_shell", arguments={"command": "echo hi"}),
            ]}],
            [{"type": "done"}],
        ])
        patch_provider(fake)

        resp = await _stream(
            client, chat["id"], prov_id,
            tools_enabled=True, tool_read_only=True,
        )
        events = await _consume_sse_events(resp)
        results = [e for e in events if e.get("type") == "tool_result"]
        assert len(results) == 1
        assert results[0]["is_error"] is True
        assert "read-only" in results[0]["result"]

    async def test_stop_generation_mid_stream(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        started = asyncio.Event()
        release = asyncio.Event()

        class GatedProvider(FakeProvider):
            async def stream_complete(self, messages, **kwargs):
                yield {"type": "token", "text": "first"}
                started.set()
                await release.wait()
                yield {"type": "token", "text": "second"}
                yield {"type": "done"}

        fake = GatedProvider([])
        patch_provider(fake)

        task = asyncio.create_task(_stream(client, chat["id"], prov_id))
        await asyncio.wait_for(started.wait(), 10)

        db_path = _db_path(tmp_test_dir)
        deadline = time.monotonic() + 5
        asst_id = None
        while time.monotonic() < deadline:
            row = await _fetchone(
                db_path,
                "SELECT id FROM messages WHERE chat_id = ? AND role = 'assistant' AND position > 0",
                chat["id"],
            )
            if row:
                asst_id = row[0]
                break
            await asyncio.sleep(0.01)
        assert asst_id, "assistant slot must exist while generation is in flight"

        stop_resp = await client.post(f"/api/stop-generation/{asst_id}")
        assert stop_resp.status_code == 200
        assert stop_resp.json() == {"ok": True}

        release.set()
        resp = await asyncio.wait_for(task, 10)
        events = await _consume_sse_events(resp)
        assert events[0]["type"] == "start"
        tokens = [e["text"] for e in events if e.get("type") == "token"]
        assert tokens == ["first"], "tokens after the stop request must be dropped"
        assert events[-1]["type"] == "done"

        asst = await _assistant_variant(db_path, chat["id"])
        assert asst["content"] == "first"

    async def test_stop_generation_unknown_message_404(self, client):
        resp = await client.post("/api/stop-generation/does-not-exist")
        assert resp.status_code == 404

    async def test_non_stream_generation(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        fake = FakeProvider([
            [
                {"type": "token", "text": "Json"},
                {"type": "token", "text": " mode"},
                {"type": "usage", "usage": {
                    "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5,
                }},
                {"type": "done"},
            ],
        ])
        patch_provider(fake)

        resp = await _stream(
            client, chat["id"], prov_id,
            samplers={"stream_enabled": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["done"] is True
        assert data["full_text"] == "Json mode"
        assert data["user_message_id"] is not None
        assert data["variant_meta"] == {}

        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        assert asst["content"] == "Json mode"

    async def test_continue_prefill_events(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        db_path = _db_path(tmp_test_dir)
        now = _now_iso()

        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), chat["id"], "user", 0, 0, now),
            )
            asst_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (asst_id, chat["id"], "assistant", 1, 0, now),
            )
            await db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), asst_id, 0, "Old text", now),
            )
            await db.commit()

        fake = FakeProvider(
            [[{"type": "token", "text": " rest"}, {"type": "done"}]],
            echoes_prefill=False,
        )
        patch_provider(fake)

        resp = await _stream(
            client, chat["id"], prov_id,
            user_message="",
            regenerate=True,
            continue_text="cont",
            continue_reasoning="pre-reason",
        )
        events = await _consume_sse_events(resp)
        reasoning_events = [e["text"] for e in events if e.get("type") == "meta" and e.get("field") == "reasoning"]
        assert reasoning_events == ["pre-reason"]
        tokens = [e["text"] for e in events if e.get("type") == "token"]
        assert tokens == ["cont", " rest"]

        asst = await _assistant_variant(db_path, chat["id"])
        assert asst["content"] == "cont rest", "continue must update the active variant in place"
        assert json.loads(asst["variant_meta"])["reasoning"] == "pre-reason"

    async def test_provider_not_found_404(self, client, patch_provider):
        chat, _ = await _setup(client)
        patch_provider(FakeProvider([[{"type": "done"}]]))
        resp = await _stream(client, chat["id"], "missing-provider")
        assert resp.status_code == 404

    async def test_stream_failure_emits_error_event(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        fake = FakeProvider([RuntimeError("boom")])
        patch_provider(fake)

        resp = await _stream(client, chat["id"], prov_id)
        events = await _consume_sse_events(resp)
        assert any(e.get("error") for e in events)
        assert await _assistant_variant(_db_path(tmp_test_dir), chat["id"]) is None, (
            "failed empty generation must roll back the assistant slot"
        )


class TestItemize:
    async def test_itemize_text(self, client):
        chat, _ = await _setup(client)
        resp = await client.post(
            "/api/itemize",
            json={"chat_id": chat["id"], "user_message": "Hello world", "attachment_ids": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tokens"] > 0
        user = next(m for m in data["messages"] if m["role"] == "user")
        assert user["parts"][0]["type"] == "text"

    async def test_itemize_image_attachment(self, client):
        chat, _ = await _setup(client)
        buf = BytesIO()
        Image.new("RGBA", (16, 16), (10, 20, 30, 255)).save(buf, format="PNG")
        upload = await client.post(
            f"/api/chats/{chat['id']}/attachments",
            files=[("files", ("pixel.png", buf.getvalue(), "image/png"))],
        )
        assert upload.status_code == 201
        att = upload.json()["attachments"][0]

        resp = await client.post(
            "/api/itemize",
            json={"chat_id": chat["id"], "user_message": "what is this", "attachment_ids": [att["id"]]},
        )
        assert resp.status_code == 200
        data = resp.json()
        user = next(m for m in data["messages"] if m["role"] == "user")
        parts = user["parts"]
        assert [p["type"] for p in parts] == ["text", "text", "image"]
        assert parts[-1]["tokens"] > 0
