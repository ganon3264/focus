"""Tests for the /api/stream endpoint abort behavior.

Verifies that when a stream is aborted (or fails) before any tokens are
produced, the database state is correct:
  - For new messages: the eagerly-inserted empty assistant row is rolled
    back, but the user message is preserved.
  - For regenerate: the old assistant message (and all its variants) MUST
    be preserved — `_rollback_assistant` must not be called because there
    is no eagerly-inserted data to roll back; the old message is a real
    message in the conversation.
"""

import json
import os
import uuid
from datetime import UTC, datetime

import aiosqlite


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _db_path(tmp_test_dir: str) -> str:
    return os.path.join(tmp_test_dir, "test.db")


async def _insert_message(
    db_path: str,
    *,
    chat_id: str,
    role: str,
    position: int,
    content: str = "",
    active_index: int = 0,
) -> tuple[str, str | None]:
    msg_id = str(uuid.uuid4())
    now = _now_iso()
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "INSERT INTO messages (id, chat_id, role, position, active_index, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (msg_id, chat_id, role, position, active_index, now),
        )
        variant_id = None
        if content:
            variant_id = str(uuid.uuid4())
            await db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (variant_id, msg_id, 0, content, now),
            )
        await db.commit()
    return msg_id, variant_id


async def _count_assistant_messages(db_path: str, chat_id: str) -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM messages WHERE chat_id = ? AND role = 'assistant'",
            (chat_id,),
        )
        row = await cur.fetchone()
        return row[0]


async def _count_variants(db_path: str, message_id: str) -> int:
    async with aiosqlite.connect(db_path) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM message_variants WHERE message_id = ?",
            (message_id,),
        )
        row = await cur.fetchone()
        return row[0]


async def _consume_sse_events(resp) -> list[dict]:
    """Consume an SSE response and return the list of parsed event payloads."""
    events: list[dict] = []
    body = resp.text
    for line in body.splitlines():
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


class _FailingProvider:
    """A provider that raises an exception before yielding, simulating
    a stream failure / abort before any tokens are produced."""

    supports_prefill = True
    echoes_prefill = True

    def __init__(self, *args, **kwargs):
        pass

    async def stream_complete(self, messages, **kwargs):
        raise RuntimeError("simulated stream failure")
        yield  # make this a generator (never reached)


class TestStreamAbortBehavior:
    async def _make_provider(self, client) -> str:
        resp = await client.post(
            "/api/providers/",
            json={
                "name": "TestProvider",
                "type": "openai_compat",
                "model": "gpt-4",
                "api_key": "sk-test",
            },
        )
        assert resp.status_code == 201
        return resp.json()["id"]

    async def test_new_message_failure_calls_rollback_assistant(self, client, tmp_test_dir):
        """When a new-message stream fails, `_rollback_assistant` MUST be
        called with the assistant message id (to clean up the eagerly
        inserted empty row)."""
        from tests.helpers import create_character, create_chat, create_persona, create_preset

        char = await create_character(client, "Char")
        persona = await create_persona(client, "P")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], persona["id"], preset["id"])
        provider_id = await self._make_provider(client)

        import focus.providers
        from focus.routers import stream as stream_module

        rollback_calls: list[str | None] = []
        original_rollback = stream_module._rollback_assistant

        async def tracking_rollback(asst_msg_id):
            rollback_calls.append(asst_msg_id)
            return await original_rollback(asst_msg_id)

        original_provider = focus.providers.create_provider
        focus.providers.create_provider = lambda row: _FailingProvider()
        stream_module.create_provider = focus.providers.create_provider
        stream_module._rollback_assistant = tracking_rollback
        try:
            resp = await client.post(
                "/api/stream",
                json={
                    "chat_id": chat["id"],
                    "provider_id": provider_id,
                    "user_message": "Hello",
                    "samplers": {"stream_enabled": True},
                    "regenerate": False,
                    "attachment_ids": [],
                },
            )
        finally:
            focus.providers.create_provider = original_provider
            stream_module.create_provider = original_provider
            stream_module._rollback_assistant = original_rollback

        events = await _consume_sse_events(resp)
        assert any(e.get("error") for e in events), (
            f"Expected an error event, got: {events}"
        )
        assert len(rollback_calls) >= 1, (
            f"_rollback_assistant must be called on new-message failure, "
            f"got calls: {rollback_calls}"
        )
        assert rollback_calls[0] is not None, (
            "_rollback_assistant must be called with a non-None assistant id"
        )

    async def test_regenerate_failure_does_not_call_rollback_assistant(self, client, tmp_test_dir):
        """When a regenerate stream fails, `_rollback_assistant` MUST NOT
        be called — the old assistant message is a real message in the
        conversation and must not be deleted."""
        from tests.helpers import create_character, create_chat, create_persona, create_preset

        char = await create_character(client, "Char")
        persona = await create_persona(client, "P")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], persona["id"], preset["id"])
        provider_id = await self._make_provider(client)
        db_path = _db_path(tmp_test_dir)

        await _insert_message(db_path, chat_id=chat["id"], role="user", position=0, content="Hi")
        old_asst_id, _ = await _insert_message(
            db_path, chat_id=chat["id"], role="assistant", position=1, content="Old"
        )

        import focus.providers
        from focus.routers import stream as stream_module

        rollback_calls: list[str | None] = []
        original_rollback = stream_module._rollback_assistant

        async def tracking_rollback(asst_msg_id):
            rollback_calls.append(asst_msg_id)
            return await original_rollback(asst_msg_id)

        original_provider = focus.providers.create_provider
        focus.providers.create_provider = lambda row: _FailingProvider()
        stream_module.create_provider = focus.providers.create_provider
        stream_module._rollback_assistant = tracking_rollback
        try:
            resp = await client.post(
                "/api/stream",
                json={
                    "chat_id": chat["id"],
                    "provider_id": provider_id,
                    "user_message": "",
                    "samplers": {"stream_enabled": True},
                    "regenerate": True,
                    "attachment_ids": [],
                },
            )
        finally:
            focus.providers.create_provider = original_provider
            stream_module.create_provider = original_provider
            stream_module._rollback_assistant = original_rollback

        events = await _consume_sse_events(resp)
        assert any(e.get("error") for e in events), (
            f"Expected an error event, got: {events}"
        )
        assert rollback_calls == [], (
            f"_rollback_assistant must NOT be called on regenerate failure, "
            f"got calls: {rollback_calls}"
        )

    async def test_regenerate_failure_preserves_old_message(self, client, tmp_test_dir):
        """When a regenerate stream fails, the old assistant message and
        all its variants must remain in the DB."""
        from tests.helpers import create_character, create_chat, create_persona, create_preset

        char = await create_character(client, "Char")
        persona = await create_persona(client, "P")
        preset = await create_preset(client, "Pr")
        chat = await create_chat(client, char["id"], persona["id"], preset["id"])
        provider_id = await self._make_provider(client)
        db_path = _db_path(tmp_test_dir)

        await _insert_message(db_path, chat_id=chat["id"], role="user", position=0, content="Hi")
        old_asst_id, _ = await _insert_message(
            db_path,
            chat_id=chat["id"],
            role="assistant",
            position=1,
            content="Old response",
        )
        now = _now_iso()
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO message_variants (id, message_id, variant_index, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), old_asst_id, 1, "Another variant", now),
            )
            await db.commit()

        assert await _count_variants(db_path, old_asst_id) == 2

        import focus.providers
        from focus.routers import stream as stream_module

        async def _no_rollback(asst_msg_id):
            return None

        original_provider = focus.providers.create_provider
        original_rollback = stream_module._rollback_assistant
        focus.providers.create_provider = lambda row: _FailingProvider()
        stream_module.create_provider = focus.providers.create_provider
        # Replace _rollback_assistant with a no-op for regenerate (which it
        # shouldn't be called for anyway). The real rollback uses the
        # production DB_PATH so it would touch the wrong database.
        stream_module._rollback_assistant = _no_rollback
        try:
            resp = await client.post(
                "/api/stream",
                json={
                    "chat_id": chat["id"],
                    "provider_id": provider_id,
                    "user_message": "",
                    "samplers": {"stream_enabled": True},
                    "regenerate": True,
                    "attachment_ids": [],
                },
            )
        finally:
            focus.providers.create_provider = original_provider
            stream_module.create_provider = original_provider
            stream_module._rollback_assistant = original_rollback

        events = await _consume_sse_events(resp)
        assert any(e.get("error") for e in events), (
            f"Expected an error event, got: {events}"
        )
        assert await _count_assistant_messages(db_path, chat["id"]) == 1, (
            "Old assistant message must be preserved on regenerate failure"
        )
        assert await _count_variants(db_path, old_asst_id) == 2, (
            "All old variants must be preserved on regenerate failure"
        )
