"""End-to-end harness: the real app, in a real browser, against one fake upstream.

Everything below the provider's wire format is production code: prompt assembly,
quirks, streaming, segment persistence, HTMX swaps, Alpine state, SQLite. The
only stand-in is the LLM's HTTP endpoint, which is the one thing a test cannot
own for real.
"""

import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]

DEFAULT_REPLY = "Hello from the fake model."
CHUNK_DELAY = 0.0


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeLLM:
    """OpenAI-compatible upstream. Scripted replies, recorded requests."""

    def __init__(self):
        self.replies: list[str] = []
        self.requests: list[dict] = []
        self.chunk_delay = CHUNK_DELAY
        self._lock = threading.Lock()

    def reply(self, text: str) -> None:
        with self._lock:
            self.replies.append(text)

    def next_reply(self) -> str:
        with self._lock:
            return self.replies.pop(0) if self.replies else DEFAULT_REPLY

    def last_request_messages(self) -> list[dict]:
        assert self.requests, "the app never called the upstream model"
        return self.requests[-1]["messages"]


def _make_handler(state: FakeLLM):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def _json(self, payload: dict) -> None:
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _chunk(self, text: str) -> None:
            data = text.encode()
            self.wfile.write(b"%x\r\n%s\r\n" % (len(data), data))
            self.wfile.flush()

        def do_GET(self):
            if self.path.endswith("/models"):
                self._json({"object": "list", "data": [{"id": "fake-model", "object": "model"}]})
            else:
                self._json({})

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            payload = json.loads(self.rfile.read(length) or b"{}")
            with state._lock:
                state.requests.append(payload)

            text = state.next_reply()

            # openai_compat echoes the prefill: on continue the partial assistant
            # turn is the last message, and the provider resends it before the
            # new tokens. Emulate that, or the app (correctly, for its profile)
            # treats the stream as already carrying the full text.
            messages = payload.get("messages") or []
            if messages and messages[-1].get("role") == "assistant":
                prefill = messages[-1].get("content")
                if isinstance(prefill, str):
                    text = prefill + text

            base = {
                "id": "chatcmpl-fake",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": payload.get("model", "fake-model"),
            }

            if not payload.get("stream"):
                self._json(
                    {
                        "id": "chatcmpl-fake",
                        "object": "chat.completion",
                        "created": 0,
                        "model": payload.get("model", "fake-model"),
                        "choices": [
                            {
                                "index": 0,
                                "message": {"role": "assistant", "content": text},
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                    }
                )
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()

            for piece in [text[i : i + 8] for i in range(0, len(text), 8)]:
                delta = {**base, "choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}]}
                self._chunk(f"data: {json.dumps(delta)}\n\n")
                if state.chunk_delay:
                    time.sleep(state.chunk_delay)

            final = {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]}
            self._chunk(f"data: {json.dumps(final)}\n\n")
            self._chunk(
                "data: "
                + json.dumps({**base, "choices": [], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}})
                + "\n\n"
            )
            self._chunk("data: [DONE]\n\n")
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()

    return Handler


@pytest.fixture(scope="session")
def llm():
    state = FakeLLM()
    port = _free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(state))
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    state.base_url = f"http://127.0.0.1:{port}/v1"
    yield state
    server.shutdown()


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    port = _free_port()
    data_dir = tmp_path_factory.mktemp("e2e-data")
    env = {
        **os.environ,
        "FOCUS_DATA_DIR": str(data_dir),
        "FOCUS_ASSETS_DIR": str(data_dir / "assets"),
        "FOCUS_BACKUPS_DIR": str(data_dir / "backups"),
        "FOCUS_CACHE_STATIC": "0",
        "FOCUS_DEBUG": "0",
    }
    for sub in ("assets", "backups"):
        (data_dir / sub).mkdir(parents=True, exist_ok=True)

    log = open(data_dir / "app.log", "wb")
    proc = subprocess.Popen(
        [sys.executable, "main.py", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )

    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 60
    import urllib.error
    import urllib.request

    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError((data_dir / "app.log").read_text())
        try:
            urllib.request.urlopen(base_url + "/static/fonts.css", timeout=1).read()
            break
        except (urllib.error.URLError, ConnectionError, OSError):
            time.sleep(0.2)
    else:
        raise RuntimeError("app did not start:\n" + (data_dir / "app.log").read_text())

    class App:
        url = base_url
        db_path = data_dir / "focus.db"

    yield App
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
    log.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def browser():
    async with async_playwright() as p:
        instance = await p.chromium.launch(
            executable_path="/usr/bin/google-chrome", args=["--no-sandbox"]
        )
        yield instance
        await instance.close()


@pytest_asyncio.fixture(loop_scope="session")
async def page(browser):
    context = await browser.new_context(viewport={"width": 1600, "height": 1000})
    page = await context.new_page()
    page.set_default_timeout(15_000)
    page.js_errors = []
    page.on("pageerror", lambda exc: page.js_errors.append(str(exc)))
    yield page
    await context.close()


class World:
    """Base entities and the active provider, created once over the real API.

    Setup goes through HTTP because the point of these tests is the browser;
    every assertion that follows is about what a click did.
    """

    def __init__(self, client, character, preset, provider):
        self.client = client
        self.character = character
        self.preset = preset
        self.provider = provider

    def new_chat(self, title="E2E chat"):
        res = self.client.post(
            "/api/chats/",
            json={
                "title": title,
                "character_id": self.character["id"],
                "preset_id": self.preset["id"],
                "provider_id": self.provider["id"],
            },
        )
        res.raise_for_status()
        return res.json()

    def variants(self, chat_id):
        res = self.client.get(f"/api/chats/{chat_id}/messages")
        res.raise_for_status()
        return res.json()


@pytest.fixture(scope="session")
def world(app, llm):
    import httpx

    with httpx.Client(base_url=app.url, timeout=30) as client:
        character = client.post(
            "/api/characters/",
            json={
                "name": "Aria",
                "description": "A cartographer who has never left the valley.",
                "personality": "Patient",
                "scenario": "A map room at dusk.",
            },
        )
        assert character.status_code == 201, character.text
        preset = client.post("/api/presets/", data={"name": "E2E Preset"})
        assert preset.status_code == 201, preset.text
        provider = client.post(
            "/api/providers/",
            json={
                "name": "Fake Upstream",
                "type": "openai_compat",
                "base_url": llm.base_url,
                "model": "fake-model",
                "api_key": "test-key",
            },
        )
        assert provider.status_code == 201, provider.text
        provider = provider.json()

        active = client.put(
            "/api/settings/active-provider",
            json={"provider_id": provider["id"], "provider_type": "openai_compat"},
        )
        assert active.status_code == 200, active.text

        yield World(client, character.json(), preset.json(), provider)


@pytest.fixture
def db(app):
    conn = sqlite3.connect(f"file:{app.db_path}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
