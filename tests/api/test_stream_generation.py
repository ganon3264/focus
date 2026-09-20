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
        if content is not None:
            await db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at)"
                " VALUES (?, ?, 0, ?, ?)",
                (str(uuid.uuid4()), msg_id, content, now),
            )
        await db.commit()
    return msg_id


async def _message_rows(db_path, chat_id):
    return await _fetchall(
        db_path,
        "SELECT m.role, m.position, m.id,"
        " (SELECT COUNT(*) FROM message_variants mv WHERE mv.message_id = m.id) AS vcount"
        " FROM messages m WHERE m.chat_id = ? ORDER BY m.position",
        chat_id,
    )


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

    async def test_tool_iteration_cap_still_finalizes(self, client, tmp_test_dir, patch_provider):
        """Hitting the per-chat tool iteration cap must emit done and persist segments.

        Regression: the loop used to fall off the end without a done event, so
        _finalize_gen never ran and the last checkpoint's NULL segments_json
        wiped every tool-call boundary from the re-rendered message.
        """
        chat, prov_id = await _setup(client)
        patch = await client.patch(f"/api/chats/{chat['id']}", json={"max_tool_iterations": 3})
        assert patch.status_code == 200

        rounds = [
            [
                {"type": "token", "text": f"step{i} "},
                {"type": "tool_calls", "calls": [
                    ToolCall(id=f"c{i}", name="no_such_tool", arguments={}),
                ]},
            ]
            for i in range(3)
        ]
        fake = FakeProvider(rounds)
        patch_provider(fake)

        resp = await _stream(
            client, chat["id"], prov_id,
            user_message="go", tools_enabled=True, tool_read_only=False,
        )
        events = await _consume_sse_events(resp)
        assert events[-1]["type"] == "done", "iteration cap must still signal completion"
        assert fake.calls == 3

        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        assert asst["content"] == "".join(f"step{i} " for i in range(3))
        segments = json.loads(asst["segments_json"])
        boundaries = [s for s in segments if s["type"] == "tool_boundary"]
        assert len(boundaries) == 3
        assert [b["tool_calls"][0]["id"] for b in boundaries] == [f"c{i}" for i in range(3)]

        tool_rows = await _fetchall(
            _db_path(tmp_test_dir),
            "SELECT COUNT(*) FROM tool_calls WHERE chat_id = ?",
            chat["id"],
        )
        assert tool_rows[0][0] == 3

        stored = await _fetchone(
            _db_path(tmp_test_dir),
            "SELECT max_tool_iterations FROM chats WHERE id = ?",
            chat["id"],
        )
        assert stored[0] == 3

    async def test_max_tool_iterations_clamped(self, client, tmp_test_dir):
        chat, _ = await _setup(client)
        db_path = _db_path(tmp_test_dir)

        stored = await _fetchone(
            db_path, "SELECT max_tool_iterations FROM chats WHERE id = ?", chat["id"]
        )
        assert stored[0] == 25, "default cap is 25"

        for sent, expected in ((0, 0), (-5, 0), (9999, 100)):
            await client.patch(f"/api/chats/{chat['id']}", json={"max_tool_iterations": sent})
            stored = await _fetchone(
                db_path, "SELECT max_tool_iterations FROM chats WHERE id = ?", chat["id"]
            )
            assert stored[0] == expected, f"{sent} must clamp to {expected}"

    async def test_zero_tool_iterations_means_unlimited(self, client, tmp_test_dir, patch_provider):
        """0 disables the cap; the loop ends only when the model stops calling tools."""
        chat, prov_id = await _setup(client)
        await client.patch(f"/api/chats/{chat['id']}", json={"max_tool_iterations": 0})

        rounds = [
            [
                {"type": "token", "text": f"step{i} "},
                {"type": "tool_calls", "calls": [
                    ToolCall(id=f"c{i}", name="no_such_tool", arguments={}),
                ]},
            ]
            for i in range(5)
        ]
        rounds.append([{"type": "token", "text": "final"}, {"type": "done"}])
        fake = FakeProvider(rounds)
        patch_provider(fake)

        resp = await _stream(
            client, chat["id"], prov_id,
            user_message="go", tools_enabled=True, tool_read_only=False,
        )
        events = await _consume_sse_events(resp)
        assert events[-1]["type"] == "done"
        assert fake.calls == 6

        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        segments = json.loads(asst["segments_json"])
        boundaries = [s for s in segments if s["type"] == "tool_boundary"]
        assert len(boundaries) == 5

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
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = await _consume_sse_events(resp)
        assert events[0]["type"] == "start"
        # Buffered mode never emits per-delta tokens; the finished text is
        # replayed as a single token just before done.
        tokens = [e["text"] for e in events if e.get("type") == "token"]
        assert tokens == ["Json mode"]
        assert events[-1]["type"] == "done"

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


class TestTurnDecision:
    """The server owns whether a request is a new turn or a regenerate."""

    async def test_regenerate_with_user_message_becomes_new_turn(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        patch_provider(FakeProvider([[{"type": "token", "text": "one"}, {"type": "done"}]]))
        await _stream(client, chat["id"], prov_id, user_message="First")
        db_path = _db_path(tmp_test_dir)

        patch_provider(FakeProvider([[{"type": "token", "text": "two"}, {"type": "done"}]]))
        resp = await _stream(
            client, chat["id"], prov_id,
            user_message="Second", regenerate=True,
        )
        assert resp.status_code == 200
        await _consume_sse_events(resp)

        rows = await _message_rows(db_path, chat["id"])
        assert [r["role"] for r in rows] == ["user", "assistant", "user", "assistant"]
        assert [r["position"] for r in rows] == [0, 1, 2, 3]
        assert all(r["vcount"] == 1 for r in rows), (
            "a user message must never be turned into a variant of the previous turn"
        )

    async def test_empty_send_replies_to_pending_user_turn(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        db_path = _db_path(tmp_test_dir)
        await _insert_message(db_path, chat["id"], "assistant", 0, "Greeting")
        await _insert_message(db_path, chat["id"], "user", 1, "Pending")

        patch_provider(FakeProvider([[{"type": "token", "text": "reply"}, {"type": "done"}]]))
        resp = await _stream(client, chat["id"], prov_id, user_message="", regenerate=False)
        assert resp.status_code == 200
        await _consume_sse_events(resp)

        rows = await _message_rows(db_path, chat["id"])
        assert [r["role"] for r in rows] == ["assistant", "user", "assistant"]
        assert rows[-1]["position"] == 2
        assert rows[0]["vcount"] == 1, "the greeting must not receive a variant"

    async def test_regenerate_with_pending_user_turn_becomes_reply(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        db_path = _db_path(tmp_test_dir)
        await _insert_message(db_path, chat["id"], "assistant", 0, "Greeting")
        await _insert_message(db_path, chat["id"], "user", 1, "Pending")

        patch_provider(FakeProvider([[{"type": "token", "text": "reply"}, {"type": "done"}]]))
        resp = await _stream(client, chat["id"], prov_id, user_message="", regenerate=True)
        assert resp.status_code == 200
        await _consume_sse_events(resp)

        rows = await _message_rows(db_path, chat["id"])
        assert [r["role"] for r in rows] == ["assistant", "user", "assistant"]
        assert rows[0]["vcount"] == 1, "the greeting must not receive a variant"

    async def test_empty_send_with_assistant_last_is_rejected(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        db_path = _db_path(tmp_test_dir)
        await _insert_message(db_path, chat["id"], "assistant", 0, "Greeting")
        await _insert_message(db_path, chat["id"], "user", 1, "Hi")
        await _insert_message(db_path, chat["id"], "assistant", 2, "Hello")

        patch_provider(FakeProvider([[{"type": "token", "text": "nope"}, {"type": "done"}]]))
        resp = await _stream(client, chat["id"], prov_id, user_message="", regenerate=False)
        assert resp.status_code == 400
        assert "Nothing to reply to" in resp.json()["detail"]


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


class RetryableError(Exception):
    """Provider error carrying an HTTP status for retry classification."""

    def __init__(self, status):
        super().__init__(f"HTTP {status}")
        self.status_code = status


async def _set_retry(client, prov_id, **retry):
    resp = await client.patch(f"/api/providers/{prov_id}", json={"params": {"retry": retry}})
    assert resp.status_code == 200


class TestAutoRetry:
    async def test_retries_before_first_token_then_succeeds(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        await _set_retry(client, prov_id, base_delay=0, max_delay=0, on_rate_limit=True)
        fake = FakeProvider([
            RetryableError(429),
            [{"type": "token", "text": "Hi"}, {"type": "done"}],
        ])
        patch_provider(fake)

        events = await _consume_sse_events(await _stream(client, chat["id"], prov_id))
        retries = [e for e in events if e.get("type") == "retry"]
        assert len(retries) == 1
        assert retries[0]["attempt"] == 1 and retries[0]["max"] == 5
        assert retries[0]["kind"] == "rate_limit"
        assert retries[0]["status"] == 429
        assert retries[0]["reason"] == "HTTP 429"
        assert [e["text"] for e in events if e.get("type") == "token"] == ["Hi"]
        assert fake.calls == 2

        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        assert asst["content"] == "Hi"

    async def test_disabled_retry_surfaces_error_immediately(self, client, patch_provider):
        chat, prov_id = await _setup(client)
        await _set_retry(client, prov_id, enabled=False)
        fake = FakeProvider([RetryableError(429)])
        patch_provider(fake)

        events = await _consume_sse_events(await _stream(client, chat["id"], prov_id))
        assert [e.get("type") for e in events if e.get("type") == "retry"] == []
        assert any(e.get("type") == "error" for e in events)
        assert fake.calls == 1

    async def test_max_retries_exhausted(self, client, patch_provider):
        chat, prov_id = await _setup(client)
        await _set_retry(client, prov_id, base_delay=0, max_delay=0, max_retries=3)
        fake = FakeProvider([
            RetryableError(503), RetryableError(503),
            RetryableError(503), RetryableError(503),
        ])
        patch_provider(fake)

        events = await _consume_sse_events(await _stream(client, chat["id"], prov_id))
        assert len([e for e in events if e.get("type") == "retry"]) == 3
        assert any(e.get("type") == "error" for e in events)
        assert fake.calls == 4

    async def test_no_retry_after_token_emitted(self, client, patch_provider):
        chat, prov_id = await _setup(client)
        await _set_retry(client, prov_id, base_delay=0, max_delay=0, on_rate_limit=True)

        class FailAfterTokenProvider:
            supports_prefill = True
            echoes_prefill = True
            supports_tools = True

            def __init__(self):
                self.calls = 0

            async def stream_complete(self, messages, **kwargs):
                self.calls += 1
                yield {"type": "token", "text": "partial"}
                raise RetryableError(429)

        fake = FailAfterTokenProvider()
        patch_provider(fake)

        events = await _consume_sse_events(await _stream(client, chat["id"], prov_id))
        assert [e for e in events if e.get("type") == "retry"] == []
        assert any(e.get("type") == "error" for e in events)
        assert fake.calls == 1

    async def test_non_retryable_status_not_retried(self, client, patch_provider):
        chat, prov_id = await _setup(client)
        await _set_retry(client, prov_id, base_delay=0, max_delay=0)
        fake = FakeProvider([RetryableError(401)])
        patch_provider(fake)

        events = await _consume_sse_events(await _stream(client, chat["id"], prov_id))
        assert [e for e in events if e.get("type") == "retry"] == []
        assert any(e.get("type") == "error" for e in events)
        assert fake.calls == 1

    async def test_error_prefers_provider_message(self, client, patch_provider):
        """The final error surfaces the SDK's clean ``.message``, not its raw
        ``str()`` (which for Google appends the whole JSON body)."""
        chat, prov_id = await _setup(client)
        await _set_retry(client, prov_id, enabled=False)

        class MessageError(Exception):
            message = "This model is busy, try again."

            def __init__(self):
                super().__init__("503 UNAVAILABLE. {'error': {'code': 503}}")
                self.status_code = 503

        fake = FakeProvider([MessageError()])
        patch_provider(fake)

        events = await _consume_sse_events(await _stream(client, chat["id"], prov_id))
        errors = [e for e in events if e.get("type") == "error"]
        assert errors and errors[0]["error"] == "This model is busy, try again."

    async def test_extra_status_code_extends_retry_set(self, client, patch_provider):
        chat, prov_id = await _setup(client)
        await _set_retry(client, prov_id, base_delay=0, max_delay=0, extra_statuses=[418])
        fake = FakeProvider([
            RetryableError(418),
            [{"type": "token", "text": "ok"}, {"type": "done"}],
        ])
        patch_provider(fake)

        events = await _consume_sse_events(await _stream(client, chat["id"], prov_id))
        assert len([e for e in events if e.get("type") == "retry"]) == 1
        assert [e["text"] for e in events if e.get("type") == "token"] == ["ok"]
        assert fake.calls == 2

    async def test_empty_response_is_an_error(self, client, tmp_test_dir, patch_provider):
        chat, prov_id = await _setup(client)
        fake = FakeProvider([[{"type": "done"}]])
        patch_provider(fake)

        events = await _consume_sse_events(await _stream(client, chat["id"], prov_id))
        errors = [e for e in events if e.get("type") == "error"]
        assert errors and "empty" in errors[0]["error"].lower()

        # The eagerly-inserted assistant row must be rolled back, not left blank.
        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        assert asst is None
        assert fake.calls == 1

    async def test_empty_response_reports_safety_finish_reason(self, client, patch_provider):
        chat, prov_id = await _setup(client)
        fake = FakeProvider([[{"type": "done", "finish_reason": "SAFETY"}]])
        patch_provider(fake)

        events = await _consume_sse_events(await _stream(client, chat["id"], prov_id))
        errors = [e for e in events if e.get("type") == "error"]
        assert errors
        assert "safety" in errors[0]["error"].lower()
        assert "SAFETY" in errors[0]["error"]

    async def test_new_generation_supersedes_retrying_one(
        self, client, tmp_test_dir, patch_provider
    ):
        """A newer generation in the same chat must stop an older one that is
        sleeping in a retry backoff, instead of letting it keep retrying on a
        stale provider (e.g. after the user swapped the API key)."""
        chat, prov_id = await _setup(client)
        await _set_retry(client, prov_id, base_delay=10, max_delay=10, on_rate_limit=True)

        class FirstFailsThenSucceeds:
            supports_prefill = True
            echoes_prefill = True
            supports_tools = True

            def __init__(self):
                self.calls = 0
                self.first_call = asyncio.Event()

            async def stream_complete(self, messages, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    self.first_call.set()
                    raise RetryableError(429)
                yield {"type": "token", "text": "second"}
                yield {"type": "done"}

        fake = FirstFailsThenSucceeds()
        patch_provider(fake)

        task1 = asyncio.create_task(_stream(client, chat["id"], prov_id, user_message="One"))
        await asyncio.wait_for(fake.first_call.wait(), 5)
        await asyncio.sleep(0.05)  # settle into the 10s retry backoff

        events2 = await _consume_sse_events(
            await _stream(client, chat["id"], prov_id, user_message="Two")
        )
        assert [e["text"] for e in events2 if e.get("type") == "token"] == ["second"]

        events1 = await _consume_sse_events(await asyncio.wait_for(task1, 10))
        assert [e for e in events1 if e.get("type") in ("done", "error")] == []
        # The superseded run must not have reached the provider again.
        assert fake.calls == 2

        # Only the winning generation's variant exists; the stale run neither
        # saved its (empty) output nor stranded an assistant slot.
        variants = await _fetchall(
            _db_path(tmp_test_dir),
            "SELECT mv.content FROM messages m JOIN message_variants mv ON mv.message_id = m.id"
            " WHERE m.chat_id = ? AND m.role = 'assistant' AND m.position > 0",
            chat["id"],
        )
        assert [v["content"] for v in variants] == ["second"]

    async def test_provider_update_stops_retrying_generation(self, client, patch_provider):
        """Editing a provider's request config (e.g. swapping the API key) must
        stop generations bound to it instead of letting them retry the old key."""
        chat, prov_id = await _setup(client)
        await _set_retry(client, prov_id, base_delay=10, max_delay=10, on_rate_limit=True)

        class FirstFails:
            supports_prefill = True
            echoes_prefill = True
            supports_tools = True

            def __init__(self):
                self.calls = 0
                self.first_call = asyncio.Event()

            async def stream_complete(self, messages, **kwargs):
                self.calls += 1
                if self.calls == 1:
                    self.first_call.set()
                    raise RetryableError(429)
                yield {"type": "token", "text": "should not happen"}
                yield {"type": "done"}

        fake = FirstFails()
        patch_provider(fake)

        task = asyncio.create_task(_stream(client, chat["id"], prov_id))
        await asyncio.wait_for(fake.first_call.wait(), 5)
        await asyncio.sleep(0.05)  # settle into the retry backoff

        resp = await client.patch(f"/api/providers/{prov_id}", json={"model": "gpt-4o"})
        assert resp.status_code == 200

        events = await _consume_sse_events(await asyncio.wait_for(task, 10))
        assert fake.calls == 1, "the changed provider must not be retried again"
        assert events[-1]["type"] == "done"

    async def test_buffered_mode_emits_retry_events(self, client, tmp_test_dir, patch_provider):
        """Non-stream (buffered) mode still surfaces retry events, while only
        replaying the finished text once so nothing partial is ever rendered."""
        chat, prov_id = await _setup(client)
        await _set_retry(client, prov_id, base_delay=0, max_delay=0, on_rate_limit=True)
        fake = FakeProvider([
            RetryableError(429),
            [{"type": "token", "text": "Recovered"}, {"type": "done"}],
        ])
        patch_provider(fake)

        resp = await _stream(client, chat["id"], prov_id, samplers={"stream_enabled": False})
        events = await _consume_sse_events(resp)
        assert len([e for e in events if e.get("type") == "retry"]) == 1
        assert [e["text"] for e in events if e.get("type") == "token"] == ["Recovered"]
        assert events[-1]["type"] == "done"
        assert fake.calls == 2

        asst = await _assistant_variant(_db_path(tmp_test_dir), chat["id"])
        assert asst["content"] == "Recovered"

    async def test_stream_flag_plumbs_to_provider(self, client, patch_provider):
        """`stream_enabled` must reach the provider as `stream` (API mode),
        not just select the transport."""
        chat, prov_id = await _setup(client)

        streaming = FakeProvider([[{"type": "token", "text": "x"}, {"type": "done"}]])
        patch_provider(streaming)
        await _consume_sse_events(await _stream(client, chat["id"], prov_id))
        assert streaming.all_kwargs[0]["stream"] is True

        buffered = FakeProvider([[{"type": "token", "text": "y"}, {"type": "done"}]])
        patch_provider(buffered)
        await _consume_sse_events(
            await _stream(client, chat["id"], prov_id, samplers={"stream_enabled": False})
        )
        assert buffered.all_kwargs[0]["stream"] is False
