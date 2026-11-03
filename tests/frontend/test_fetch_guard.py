"""Request guard: writes and partial reads go through the shared queue.

`hxGet` / `hxPost` / `hxFetch` / `hxJson` (static/js/core/hx-queue.js) serialise
requests, so two writes fired back to back commit in order and a partial is
never fetched before the write it renders committed. A raw `fetch` bypasses
that, which is only correct for transports the queue cannot carry:

- SSE readers (the generation, summary and progress streams own their abort)
- stop requests (own short timeout; queueing them would wait behind the stream)
- binary downloads / uploads whose response is not a partial
- one slow external command that must not hold the queue

Those carry a `// raw: <reason>` marker on the call line. Everything else must
use the queue, so a new raw call fails this test instead of silently
reintroducing an out-of-order race.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEARCH_DIRS = (ROOT / "static" / "js", ROOT / "partials", ROOT / "templates")
SKIP_DIRS = {"vendor", "__pycache__"}

CALL = re.compile(r"\bfetch\s*\(")
RAW = "// raw:"
COMMENT_PREFIXES = ("//", "/*", "*", "<!--", "{#")


def _files():
    for base in SEARCH_DIRS:
        for path in base.rglob("*"):
            if path.suffix not in {".js", ".html"}:
                continue
            if SKIP_DIRS & set(path.parts):
                continue
            yield path


def _lines():
    for path in _files():
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.strip().startswith(COMMENT_PREFIXES):
                continue
            yield path.relative_to(ROOT), number, line


def test_every_fetch_is_queued_or_marked():
    unmarked = [
        f"{path}:{number}: {line.strip()}" for path, number, line in _lines() if CALL.search(line) and RAW not in line
    ]
    assert not unmarked, (
        "Raw fetch bypasses the shared request queue. Use hxGet/hxPost/hxFetch/"
        "hxJson, or mark the line with `// raw: <reason>` if it is a stream, a "
        "stop request, or binary data:\n" + "\n".join(unmarked)
    )


def test_raw_markers_are_live():
    stale = [
        f"{path}:{number}: {line.strip()}" for path, number, line in _lines() if RAW in line and not CALL.search(line)
    ]
    assert not stale, "`// raw:` marker on a line without a fetch — drop it with the call:\n" + "\n".join(stale)
