import json as _json
import re as _re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from focus.extensions import ExtensionResult, ExtensionSpec
from focus.extensions.loader import find_extension
from focus.extensions.runner import run_extension


def _spawn_echo_server():
    """Start an HTTP server that echoes each request's source back as the rewrite,
    capturing every prompt. Returns ``(server, port, captured, thread)``."""
    captured = {}

    class _Echo(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            body = _json.loads(self.rfile.read(n))
            captured.setdefault("prompts", []).append(body["prompt"])
            m = _re.match(r"<\|im_start\|>source\n(.*?)<\|im_end\|>\n", body["prompt"], _re.S)
            src = m.group(1) if m else ""
            payload = _json.dumps({"content": src + " <|im_end|>"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Echo)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1], captured, thread


def _prompt_source(prompt: str) -> str:
    m = _re.match(r"<\|im_start\|>source\n(.*?)<\|im_end\|>\n", prompt, _re.S)
    return m.group(1) if m else ""


class TestExtensionSpec:
    def test_valid_spec(self):
        spec = ExtensionSpec.model_validate({
            "name": "x",
            "description": "desc",
            "command": ["python3", "x.py"],
        })
        assert spec.roles == ["assistant"]
        assert spec.needs == ["message"]

    def test_rejects_bad_role(self):
        with pytest.raises(Exception):
            ExtensionSpec.model_validate({
                "name": "x", "description": "", "command": ["echo"],
                "roles": ["system"],
            })

    def test_rejects_bad_needs(self):
        with pytest.raises(Exception):
            ExtensionSpec.model_validate({
                "name": "x", "description": "", "command": ["echo"],
                "needs": ["bogus"],
            })

    def test_rejects_bad_param_type(self):
        with pytest.raises(Exception):
            ExtensionSpec.model_validate({
                "name": "x", "description": "", "command": ["echo"],
                "params": [{"name": "p", "type": "weird"}],
            })


class TestRealExtension:
    def test_prose_rewriter_spec(self):
        spec = find_extension("prose_rewriter")
        assert spec is not None
        assert "generation_end" in spec.triggers
        assert "manual" in spec.triggers
        assert "assistant" in spec.roles

    def test_prose_rewriter_script_compiles(self):
        import py_compile
        py_compile.compile("extensions/samples/prose_rewriter.py", doraise=True)

    def test_prose_rewriter_prompt_floors(self):
        # The model pads/invents on very short input — the script must pass it
        # through unchanged rather than call the server and fabricate.
        import json as _json
        import subprocess
        spec = find_extension("prose_rewriter")
        proc = subprocess.run(
            spec.command,
            input=_json.dumps({"target": {"content": "Short."}}),
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert proc.returncode == 0
        out = _json.loads(proc.stdout)
        assert out["content"] == "Short."
        assert out["status"] == "done"

    def test_prose_rewriter_segments_preserve_structure(self):
        import json as _json
        import subprocess
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class _Probe(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                self.rfile.read(n)
                payload = _json.dumps({"content": "REWRITTEN <|im_end|>"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), _Probe)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            spec = find_extension("prose_rewriter")
            env = {
                "target": {
                    "content": "This is a long enough first sentence to clear the floor. " + "It goes on here for a bit more so it definitely crosses the byte limit.",
                    "segments": [
                        {"type": "text", "content": "This is a long enough first sentence to clear the floor. It goes on here for a bit more so it definitely crosses the byte limit."},
                        {"type": "tool_boundary", "tool_calls": [{
                            "id": "call_1", "type": "function",
                            "function": {"name": "read_file", "arguments": "{}"},
                            "result": "contents", "is_error": False,
                        }]},
                        {"type": "text", "content": "And here is a second text segment that is also long enough to be rewritten on its own."},
                    ],
                },
                "config": {"base_url": f"http://127.0.0.1:{port}"},
            }
            proc = subprocess.run(spec.command, input=_json.dumps(env), capture_output=True, text=True, timeout=30)
            assert proc.returncode == 0
            out = _json.loads(proc.stdout)
            assert out["status"] == "done"
            assert out["action"]["type"] == "create_swipe"
            segs = out["action"]["segments"]
            assert [s["type"] for s in segs] == ["text", "tool_boundary", "text"]
            assert segs[0]["content"] == "REWRITTEN"
            assert segs[1]["tool_calls"], "tool boundary must be preserved verbatim"
            assert segs[2]["content"] == "REWRITTEN"
        finally:
            server.shutdown()

    def test_prose_rewriter_calls_llamacpp_completion(self):
        import json as _json
        import subprocess
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        captured = {}

        class _Probe(BaseHTTPRequestHandler):
            def do_POST(self):
                n = int(self.headers.get("Content-Length", 0))
                captured["body"] = self.rfile.read(n)
                payload = _json.dumps({"content": "REWRITTEN REPLY <|im_end|>"}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), _Probe)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            spec = find_extension("prose_rewriter")
            env = {
                "target": {"content": "A paragraph long enough to clear the fifteen-word floor and the eighty-byte floor so that the model will actually run for real now."},
                "config": {"base_url": f"http://127.0.0.1:{port}"},
            }
            proc = subprocess.run(spec.command, input=_json.dumps(env), capture_output=True, text=True, timeout=30)
            assert proc.returncode == 0
            out = _json.loads(proc.stdout)
            assert out["status"] == "done"
            assert out["action"]["content"] == "REWRITTEN REPLY"
            request_body = _json.loads(captured["body"])
            assert request_body["prompt"].startswith("<|im_start|>source\n")
            assert request_body["stop"] == ["<|im_end|>"]
            assert request_body["n_predict"] == 512
        finally:
            server.shutdown()

    def test_prose_rewriter_splits_paragraphs(self):
        server, port, captured, thread = _spawn_echo_server()
        try:
            spec = find_extension("prose_rewriter")
            para1 = "First paragraph has enough words to clear the model floor and get rewritten as its own passage."
            para2 = "Second paragraph is also long enough to be rewritten as a separate passage for the split test."
            content = para1 + "\n\n" + para2
            env = {"target": {"content": content}, "config": {"base_url": f"http://127.0.0.1:{port}"}}
            proc = subprocess.run(spec.command, input=_json.dumps(env), capture_output=True, text=True, timeout=30)
            assert proc.returncode == 0
            out = _json.loads(proc.stdout)
            assert out["status"] == "done"
            assert out["action"]["content"] == content
            prompts = captured["prompts"]
            assert len(prompts) == 2, f"expected 2 model calls, got {len(prompts)}"
            for p in prompts:
                src = _prompt_source(p)
                assert "\n\n" not in src, "a single call must never carry a blank-line split"
                assert src in (para1, para2)
        finally:
            server.shutdown()

    def test_prose_rewriter_subchunks_long_paragraph(self):
        server, port, captured, thread = _spawn_echo_server()
        try:
            spec = find_extension("prose_rewriter")
            sentence = "The quick brown fox jumps over the lazy dog."
            content = " ".join([sentence] * 60)  # one long paragraph, no blank lines
            env = {"target": {"content": content}, "config": {"base_url": f"http://127.0.0.1:{port}", "max_chunk_chars": 1500}}
            proc = subprocess.run(spec.command, input=_json.dumps(env), capture_output=True, text=True, timeout=30)
            assert proc.returncode == 0
            out = _json.loads(proc.stdout)
            assert out["status"] == "done"
            prompts = captured["prompts"]
            assert len(prompts) > 1, "an over-budget paragraph must be sub-chunked"
            for p in prompts:
                assert len(_prompt_source(p)) <= 1500
            assert out["action"]["content"] == content
        finally:
            server.shutdown()

    def test_prose_rewriter_leaves_code_blocks_alone(self):
        server, port, captured, thread = _spawn_echo_server()
        try:
            spec = find_extension("prose_rewriter")
            para1 = "This is the first real paragraph with enough words to be rewritten and not passed through."
            code = "```python\nprint(1)\n```"
            para2 = "This is the second real paragraph, also long enough to be rewritten on its own by the model."
            content = para1 + "\n\n" + code + "\n\n" + para2
            env = {"target": {"content": content}, "config": {"base_url": f"http://127.0.0.1:{port}"}}
            proc = subprocess.run(spec.command, input=_json.dumps(env), capture_output=True, text=True, timeout=30)
            assert proc.returncode == 0
            out = _json.loads(proc.stdout)
            assert out["status"] == "done"
            prompts = captured["prompts"]
            assert len(prompts) == 2
            for p in prompts:
                assert "print(1)" not in _prompt_source(p), "code must never be fed to the prose rewriter"
            assert code in out["action"]["content"], "code fence must survive verbatim"
        finally:
            server.shutdown()

    def test_prose_rewriter_can_disable_split(self):
        server, port, captured, thread = _spawn_echo_server()
        try:
            spec = find_extension("prose_rewriter")
            content = (
                "First paragraph has enough words to clear the model floor and be rewritten as one passage."
                "\n\n"
                "Second paragraph would normally be split into its own call but stays inline with split off."
            )
            env = {"target": {"content": content}, "config": {"base_url": f"http://127.0.0.1:{port}", "split": False}}
            proc = subprocess.run(spec.command, input=_json.dumps(env), capture_output=True, text=True, timeout=30)
            assert proc.returncode == 0
            out = _json.loads(proc.stdout)
            assert out["status"] == "done"
            prompts = captured["prompts"]
            assert len(prompts) == 1, "split off must make exactly one model call"
            assert "\n\n" in _prompt_source(prompts[0]), "split off must feed the whole reply in one source block"
            assert out["action"]["content"] == content
        finally:
            server.shutdown()


class TestResultParsing:
    @pytest.mark.asyncio
    async def test_parses_json_result(self):
        spec = ExtensionSpec.model_validate({
            "name": "x", "description": "",
            "command": ["python3", "-c", "print('{\"status\":\"done\",\"content\":\"hi\"}')"],
        })
        result = await run_extension(spec, {})
        assert result.status == "done"
        assert result.content == "hi"

    @pytest.mark.asyncio
    async def test_plain_stdout_is_content(self):
        spec = ExtensionSpec.model_validate({
            "name": "x", "description": "",
            "command": ["python3", "-c", "print('hello')"],
        })
        result = await run_extension(spec, {})
        assert result.status == "done"
        assert result.content == "hello\n"

    @pytest.mark.asyncio
    async def test_nonzero_exit_is_error(self):
        spec = ExtensionSpec.model_validate({
            "name": "x", "description": "",
            "command": ["python3", "-c", "import sys; sys.exit(3)"],
        })
        result = await run_extension(spec, {})
        assert result.status == "error"
        assert "exit code 3" in result.error

    @pytest.mark.asyncio
    async def test_error_key_marks_error(self):
        spec = ExtensionSpec.model_validate({
            "name": "x", "description": "",
            "command": ["python3", "-c", "print('{\"error\":\"boom\"}')"],
        })
        result = await run_extension(spec, {})
        assert result.status == "error"
        assert result.error == "boom"

    @pytest.mark.asyncio
    async def test_bad_action_type_kept_for_validation_but_ignored(self):
        # Unknown action types are accepted by the model (deferred to apply_actions),
        # so a spec that returns one should still validate.
        result = ExtensionResult.model_validate({
            "status": "done",
            "action": {"type": "unknown_future_action", "content": "x"},
        })
        assert result.action.type == "unknown_future_action"
