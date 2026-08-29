"""Tests for the client hanging up in the middle of a generation.

A disconnect reaches the response generator as a pending cancellation
(Starlette watches ``http.disconnect`` and cancels the streaming task), so the
final save runs inside an already-cancelled scope. If that write is lost the
assistant row is stranded without a variant — both the prompt history and the
message list join messages onto variants, so the row is invisible while still
claiming a position, and a later regenerate lands on a brand new slot instead
of the stranded one.

The ``client`` fixture is asked for purely to provision the per-test database;
these tests drive the response generator directly so the cancellation lands on
the very code Starlette cancels.
"""

import asyncio
import os
import uuid

import aiosqlite
import pytest

from focus.core.models import StreamRequest
from focus.db.chats import delete_stranded_assistant_messages
from focus.routers.stream import _GenCtx, _stream_generate
from focus.routers.stream_utils import PromptCtx


def _db_path(tmp_test_dir: str) -> str:
    return os.path.join(tmp_test_dir, "test.db")


async def _fetchall(db_path: str, sql: str, params: tuple = ()):
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]


async def _insert_chat_and_slot(db_path: str, *, content: str | None = None,
                                regenerate_target: str | None = None) -> dict:
    """Create a chat with a greeting, optional user turn and one assistant slot.

    Returns ``{"chat_id": ..., "asst_msg_id": ...}`` where asst_msg_id is the
    empty assistant slot a generation would write into.
    """
    chat_id = str(uuid.uuid4())
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        now = "2026-01-01T00:00:00+00:00"
        await db.execute(
            "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, 'Chat', ?, ?)",
            (chat_id, now, now),
        )
        positions = [("assistant", 0, "Hi there")]
        if content is not None:
            positions.append(("user", 1, content))
        positions.append(("assistant", 2, None))
        asst_id = None
        for role, pos, text in positions:
            msg_id = str(uuid.uuid4())
            if role == "assistant" and text is None:
                asst_id = msg_id
            await db.execute(
                "INSERT INTO messages (id, chat_id, role, position, active_index, created_at)"
                " VALUES (?, ?, ?, ?, 0, ?)",
                (msg_id, chat_id, role, pos, now),
            )
            if text:
                await db.execute(
                    "INSERT INTO message_variants (id, message_id, variant_index, content, created_at)"
                    " VALUES (?, ?, 0, ?, ?)",
                    (str(uuid.uuid4()), msg_id, text, now),
                )
        await db.commit()
    return {"chat_id": chat_id, "asst_msg_id": asst_id}


class StallingProvider:
    """Emits *events*, then blocks as if the upstream stopped answering."""

    supports_prefill = True
    echoes_prefill = True
    supports_tools = True

    def __init__(self, events):
        self.events = list(events)
        self.entered = asyncio.Event()

    async def stream_complete(self, messages, **kwargs):
        for e in self.events:
            yield e
        self.entered.set()
        await asyncio.sleep(30)
        yield {"type": "done"}  # pragma: no cover - unreachable while stalled


def _ctx(db, chat_id, asst_msg_id, provider, *, regenerate=False, next_variant_index=0):
    body = StreamRequest(
        chat_id=chat_id,
        user_message="" if regenerate else "Hello",
        regenerate=regenerate,
    )
    return _GenCtx(
        body=body,
        prompt=PromptCtx(
            messages=[{"role": "user", "content": "Hello"}],
            asst_msg_id=asst_msg_id,
            next_variant_index=next_variant_index,
            user_msg_id=None,
        ),
        messages=[{"role": "user", "content": "Hello"}],
        gen_kwargs={},
        provider=provider,
        prov_dict={"id": "prov-1", "type": "openai_compat", "model": "test-model"},
        tools_enabled=False,
        tools_by_name={},
        tool_read_only=True,
        disable_multimodal=False,
        stop_event=asyncio.Event(),
        db=db,
    )


async def _drive_until_disconnect(ctx, provider) -> list[str]:
    """Stream into a task, then cancel it the way a disconnect would."""
    chunks: list[str] = []

    async def drain():
        async for chunk in _stream_generate(ctx):
            chunks.append(chunk)

    task = asyncio.create_task(drain())
    await asyncio.wait_for(provider.entered.wait(), timeout=5)
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    return chunks


class TestDisconnectFinalize:
    async def test_disconnect_without_content_rolls_back_slot(self, client, tmp_test_dir):
        """Nothing was generated: the empty slot must not survive the hang-up."""
        path = _db_path(tmp_test_dir)
        chat = await _insert_chat_and_slot(path, content="Hello")
        provider = StallingProvider([])

        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            ctx = _ctx(db, chat["chat_id"], chat["asst_msg_id"], provider)
            chunks = await _drive_until_disconnect(ctx, provider)

        assert 'data: {"type": "start"' in chunks[0]
        rows = await _fetchall(
            path,
            "SELECT id FROM messages WHERE id = ?", (chat["asst_msg_id"],),
        )
        assert rows == [], "empty assistant slot must be rolled back on disconnect"
        # The user turn is real and must survive.
        kept = await _fetchall(
            path,
            "SELECT m.id FROM messages m JOIN message_variants mv ON mv.message_id = m.id"
            " WHERE m.chat_id = ? AND m.role = 'user'",
            (chat["chat_id"],),
        )
        assert len(kept) == 1

    async def test_disconnect_persists_partial_text(self, client, tmp_test_dir, monkeypatch):
        """Tokens already produced must reach the DB even though we stop reading."""
        from focus.routers import stream as stream_module

        monkeypatch.setattr(stream_module, "_CHECKPOINT_INTERVAL_SECS", 0)
        path = _db_path(tmp_test_dir)
        chat = await _insert_chat_and_slot(path, content="Hello")
        provider = StallingProvider([
            {"type": "token", "text": "Half a "},
            {"type": "token", "text": "thought"},
        ])

        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            ctx = _ctx(db, chat["chat_id"], chat["asst_msg_id"], provider)
            await _drive_until_disconnect(ctx, provider)

        rows = await _fetchall(
            path,
            "SELECT mv.content FROM messages m JOIN message_variants mv ON mv.message_id = m.id"
            " WHERE m.id = ?",
            (chat["asst_msg_id"],),
        )
        assert [r["content"] for r in rows] == ["Half a thought"]

    async def test_disconnect_on_regenerate_keeps_previous_reply(self, client, tmp_test_dir):
        """A failed regenerate must not touch the reply it was replacing."""
        path = _db_path(tmp_test_dir)
        chat = await _insert_chat_and_slot(path)
        previous = await _fetchall(
            path, "SELECT id FROM messages WHERE chat_id = ? AND position = 0", (chat["chat_id"],),
        )
        provider = StallingProvider([])

        async with aiosqlite.connect(path) as db:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            ctx = _ctx(db, chat["chat_id"], previous[0]["id"], provider,
                       regenerate=True, next_variant_index=1)
            await _drive_until_disconnect(ctx, provider)

        variants = await _fetchall(
            path,
            "SELECT variant_index, content FROM message_variants WHERE message_id = ?",
            (previous[0]["id"],),
        )
        assert [v["variant_index"] for v in variants] == [0]
        assert variants[0]["content"] == "Hi there"


class TestStrandedMessageCleanup:
    async def test_only_assistant_rows_without_variants_are_dropped(self, client, tmp_test_dir):
        """The startup sweep removes invisible rows and nothing else."""
        path = _db_path(tmp_test_dir)
        chat = await _insert_chat_and_slot(path, content="Hello")
        extra_chat = str(uuid.uuid4())
        async with aiosqlite.connect(path) as db:
            await db.execute("PRAGMA foreign_keys=ON")
            now = "2026-01-01T00:00:00+00:00"
            await db.execute(
                "INSERT INTO chats (id, title, created_at, updated_at) VALUES (?, 'Other', ?, ?)",
                (extra_chat, now, now),
            )
            orphan = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO messages (id, chat_id, role, position, active_index, created_at)"
                " VALUES (?, ?, 'assistant', 3, 0, ?)",
                (orphan, extra_chat, now),
            )
            await db.commit()
            deleted = await delete_stranded_assistant_messages(db)
            await db.commit()

        assert deleted == 2
        remaining = await _fetchall(
            path,
            "SELECT id FROM messages m WHERE NOT EXISTS"
            " (SELECT 1 FROM message_variants mv WHERE mv.message_id = m.id)",
        )
        assert remaining == []
        kept = await _fetchall(
            path,
            "SELECT m.id FROM messages m JOIN message_variants mv ON mv.message_id = m.id"
            " WHERE m.chat_id = ? ORDER BY m.position",
            (chat["chat_id"],),
        )
        # Greeting and user turn survive; the empty slot was swept.
        assert len(kept) == 2
        assert chat["asst_msg_id"] not in [m["id"] for m in remaining + kept]
