#!/usr/bin/env python3
"""4chan board/thread tool for Focus.

Reads JSON from stdin with fields:
  action      "catalog" or "thread"
  board       board name (e.g. "g", "pol")
  page        catalog page (default 1, ignored when search is given)
  search      filter term — catalog searches all pages via /catalog.json (one call),
              thread filters replies by comment text
  thread_id   thread number (required for thread)
  offset      skip replies (thread only, default 0)
  limit       max replies (thread only, default 50)

Returns formatted markdown on stdout.
"""
import html
import json
import sys
import time
from html.parser import HTMLParser
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

API_BASE = "https://a.4cdn.org"
USER_AGENT = "Focus/1.0 (4chan sample tool)"
REQUEST_DELAY = 1.0

_UNIT_SUFFIXES = ["B", "KB", "MB", "GB"]

_TAG_MD = {
    "br": "\n",
    "b": "**",
    "strong": "**",
    "i": "*",
    "s": "~~",
    "pre": "```",
}


def _fmt_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0 B"
    i = 0
    f = float(size_bytes)
    while f >= 1024 and i < len(_UNIT_SUFFIXES) - 1:
        f /= 1024
        i += 1
    return f"{f:.1f} {_UNIT_SUFFIXES[i]}" if i > 0 else f"{int(f)} B"


class _CommentToMarkdown(HTMLParser):
    """Convert 4chan HTML comment bodies to plain text with markdown formatting."""

    def __init__(self):
        super().__init__()
        self.out = []
        self._a_href = None

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == "a":
            self._a_href = dict(attrs).get("href", "")
            self.out.append("[")
        elif t in _TAG_MD:
            self.out.append(_TAG_MD[t])

    def handle_endtag(self, tag):
        t = tag.lower()
        if t == "a":
            href = self._a_href or ""
            self.out.append(f"](" + href + ")")
            self._a_href = None
        elif t in _TAG_MD:
            self.out.append(_TAG_MD[t])

    def handle_data(self, data):
        self.out.append(data)

    def result(self) -> str:
        return "".join(self.out)


def _decode_com(com: str) -> str:
    com = html.unescape(com)
    parser = _CommentToMarkdown()
    parser.feed(com)
    return parser.result().strip()


def _fetch_json(path: str):
    url = f"{API_BASE}{path}"
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        if e.code == 404:
            raise RuntimeError(
                f"404 — `{path}` not found (board may not exist or thread is dead)"
            )
        raise RuntimeError(f"HTTP {e.code} for `{path}`")
    except URLError as e:
        raise RuntimeError(f"Network error: {e.reason}")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Bad JSON from `{path}`: {e}")


def _file_link_and_desc(post: dict, board: str):
    tim = post.get("tim")
    ext = post.get("ext")
    if not tim or not ext:
        return None
    url = f"https://i.4cdn.org/{board}/{tim}{ext}"
    parts = []
    fn = post.get("filename", "")
    ext_val = post.get("ext", "")
    if fn and ext_val:
        parts.append(f"{fn}{ext_val}")
    fsize = post.get("fsize")
    if fsize:
        parts.append(_fmt_size(fsize))
    w = post.get("w")
    h = post.get("h")
    if w and h:
        parts.append(f"{w}×{h}")
    desc = " — ".join(parts) if parts else ""
    return url, desc


def _format_identity(post: dict) -> str:
    """Format poster name with tripcode and capcode."""
    name = html.unescape(post.get("name", "Anonymous"))
    trip = post.get("trip", "")
    cap = post.get("capcode", "")
    name_str = name
    if trip:
        name_str += f" {trip}"
    if cap:
        name_str += f" ##{cap.upper()}##"
    return name_str


def _op_header(op: dict, board: str) -> list[str]:
    lines = []
    no = op.get("no", "?")
    sub = html.unescape(op.get("sub", "") or "")
    title = f"\"{sub}\"" if sub else "(no subject)"
    lines.append(f"# /{board}/ — Thread {no} — {title}")
    lines.append("")

    now = op.get("now", "")
    pid = op.get("id", "")
    op_line = f"**{_format_identity(op)}**"
    if now:
        op_line += f" — {now}"
    if pid:
        op_line += f" — ID:{pid}"
    lines.append(op_line)

    stats = f"Replies: {op.get('replies', 0)} | Images: {op.get('images', 0)}"
    ips = op.get("unique_ips")
    if ips is not None:
        stats += f" | Unique IPs: {ips}"
    if op.get("archived"):
        stats += " | Archived"
    if op.get("bumplimit"):
        stats += " | Bumplimit"
    if op.get("imagelimit"):
        stats += " | Imagelimit"
    lines.append(stats)
    lines.append("")

    fl = _file_link_and_desc(op, board)
    if fl:
        lines.append(f"[{fl[1]}]({fl[0]})" if fl[1] else fl[0])
        lines.append("")

    com = _decode_com(op.get("com", "") or "")
    if com:
        lines.append(com)
        lines.append("")

    return lines


def _reply_header(post: dict) -> str:
    no = post.get("no", "???")
    now = post.get("now", "")
    pid = post.get("id", "")
    parts = [f"### Reply #{no}", f"**{_format_identity(post)}**"]
    if now:
        parts.append(f"*{now}*")
    if pid:
        parts.append(f"ID:{pid}")
    return " — ".join(parts)


def _render_reply(reply: dict, board: str) -> list[str]:
    lines = [_reply_header(reply), ""]
    fl = _file_link_and_desc(reply, board)
    if fl:
        lines.append(f"- [{fl[1]}]({fl[0]})" if fl[1] else f"- {fl[0]}")
        lines.append("")
    com = _decode_com(reply.get("com", "") or "")
    if com:
        lines.append(com)
        lines.append("")
    return lines


def _format_thread_entry(op: dict, board: str) -> list[str]:
    lines = []
    no = op.get("no", "?")
    sub = html.unescape(op.get("sub", "") or "")
    com = _decode_com(op.get("com", "") or "")
    replies = op.get("replies", 0)
    images = op.get("images", 0)

    title = f"Thread {no}" + (f" — \"{sub}\"" if sub else "")
    lines.append(f"### {title}")

    flags = []
    for flag in ("sticky", "closed", "bumplimit", "imagelimit"):
        if op.get(flag):
            flags.append(flag.capitalize())
    flag_str = f" [{', '.join(flags)}]" if flags else ""
    lines.append(f"- Replies: {replies} | Images: {images}{flag_str}")

    fl = _file_link_and_desc(op, board)
    if fl:
        lines.append(f"- [{fl[1]}]({fl[0]})" if fl[1] else f"- {fl[0]}")

    if com:
        snippet = com[:300].replace("\n", " ")
        if len(com) > 300:
            snippet += "..."
        lines.append(f"> {snippet}")
    lines.append("")

    return lines


def action_catalog(board: str, page: int, search_term: str = "") -> str:
    if search_term:
        data = _fetch_json(f"/{board}/catalog.json")
        if not isinstance(data, list):
            raise RuntimeError(f"Unexpected catalog response type: {type(data).__name__}")

        term_lower = search_term.lower()
        matched = []

        for page_data in data:
            threads = page_data.get("threads", []) if isinstance(page_data, dict) else []
            for t in threads:
                sub = (t.get("sub", "") or "").lower()
                com_decoded = _decode_com(t.get("com", "") or "").lower()
                if term_lower in sub or term_lower in com_decoded:
                    matched.append(t)

        lines = [f"# /{board}/ — Search: \"{search_term}\"", ""]
        lines.append(f"**{len(matched)} matching threads**\n")

        for op in matched:
            lines.extend(_format_thread_entry(op, board))

        return "\n".join(lines).strip()

    data = _fetch_json(f"/{board}/{page}.json")
    if isinstance(data, dict) and "threads" in data:
        threads = data["threads"]
    elif isinstance(data, list):
        threads = data
    else:
        raise RuntimeError(f"Unexpected catalog response type: {type(data).__name__}")

    lines = [f"# /{board}/ — Page {page}", ""]
    lines.append(f"**{len(threads)} threads**\n")

    for t in threads:
        posts = t.get("posts") if isinstance(t, dict) else None
        op = posts[0] if posts else t
        lines.extend(_format_thread_entry(op, board))

    return "\n".join(lines).strip()


def action_thread(board: str, thread_id: int, offset: int = 0, limit: int = 50, search_term: str = "") -> str:
    data = _fetch_json(f"/{board}/thread/{thread_id}.json")
    if not isinstance(data, dict) or "posts" not in data:
        raise RuntimeError(f"Unexpected response format for thread {thread_id}")
    posts = data["posts"]
    if not posts:
        return f"# /{board}/ — Thread {thread_id}\n\n*(empty — no posts returned)*\n"

    op = posts[0]
    replies = posts[1:]
    lines = _op_header(op, board)

    if not replies:
        lines.append("*(no replies yet)*\n")
        return "\n".join(lines).strip()

    limit = max(0, min(limit, 100))
    offset = max(0, offset)

    if search_term:
        term_lower = search_term.lower()
        filtered = [
            r for r in replies
            if term_lower in (_decode_com(r.get("com", "") or "").lower())
        ]

        if not filtered:
            lines.append(f"*(no replies matching \"{search_term}\")*\n")
            return "\n".join(lines).strip()

        selected = filtered[offset:offset + limit]
        if not selected:
            lines.append(f"*(no matching replies at offset {offset} — {len(filtered)} total matches)*\n")
            return "\n".join(lines).strip()

        shown_range = f"replies {offset + 1}–{offset + len(selected)}"
        lines.append(f"---\n\n**{shown_range} of {len(filtered)} matching replies for \"{search_term}\"**\n")
    else:
        selected = replies[offset:offset + limit]
        if not selected:
            lines.append(f"*(no replies at offset {offset} — thread has {len(replies)} replies)*\n")
            return "\n".join(lines).strip()

        shown_range = f"replies {offset + 1}–{offset + len(selected)}"
        lines.append(f"---\n\n**{shown_range} of {len(replies)} replies shown**\n")

    for r in selected:
        lines.extend(_render_reply(r, board))

    return "\n".join(lines).strip()


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"Invalid JSON on stdin: {e}"}))
        sys.exit(1)

    action = data.get("action", "").strip().lower()
    board = data.get("board", "").strip()
    page = int(data["page"]) if "page" in data else 1
    thread_id = data.get("thread_id")
    offset = int(data["offset"]) if "offset" in data else 0
    limit = int(data["limit"]) if "limit" in data else 50
    search_term = data.get("search", "").strip()

    if action not in ("catalog", "thread"):
        print(json.dumps({"error": "action must be 'catalog' or 'thread'"}))
        sys.exit(1)

    if not board:
        print(json.dumps({"error": "board is required"}))
        sys.exit(1)

    if action == "thread" and not thread_id:
        print(json.dumps({"error": "thread_id is required when action is 'thread'"}))
        sys.exit(1)

    try:
        if action == "catalog":
            result = action_catalog(board, page, search_term)
        else:
            result = action_thread(board, int(thread_id), offset, limit, search_term)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    print(json.dumps({"output": result}))
    time.sleep(REQUEST_DELAY)


if __name__ == "__main__":
    main()
