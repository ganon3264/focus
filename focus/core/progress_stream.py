import asyncio
import logging

from fastapi.responses import StreamingResponse

from focus.core.utils import sse_event

logger = logging.getLogger("focus.progress")


def progress_stream(run) -> StreamingResponse:
    """Run ``run(progress)`` while streaming its progress as SSE.

    ``run`` is an async callable that receives the ``progress`` reporter —
    ``await progress(label, current=0, total=0)`` — and returns the payload of
    the final ``done`` event. Reported work happens in a task so the reporter's
    stages reach the client as they complete rather than all at the end.
    """

    async def events():
        queue: asyncio.Queue = asyncio.Queue()

        async def progress(label: str, current: int = 0, total: int = 0) -> None:
            await queue.put(
                {"type": "progress", "label": label, "current": current, "total": total}
            )
            # Nothing else yields inside the blocking stages (filesystem walks,
            # VACUUM), so let the generator flush before the next one starts.
            await asyncio.sleep(0)

        async def worker() -> None:
            try:
                result = await run(progress)
                await queue.put({"type": "done", "result": result})
            except Exception as exc:
                logger.exception("Background progress task failed")
                await queue.put({"type": "error", "error": str(exc)})

        task = asyncio.create_task(worker())
        try:
            while True:
                event = await queue.get()
                yield sse_event(event)
                if event["type"] in ("done", "error"):
                    break
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
