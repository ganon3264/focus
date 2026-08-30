import pytest

from focus.extensions import ExtensionResult, ExtensionSpec
from focus.extensions.loader import find_extension
from focus.extensions.runner import run_extension


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
