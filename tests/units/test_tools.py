"""Unit tests for tool runtime limits and URL safety (focus/tools/builtin.py)."""

import base64
from io import BytesIO

import pytest
from PIL import Image

from focus.core.media import set_image_format
from focus.tools.builtin import (
    _MAX_SHELL_TIMEOUT,
    _check_url_safe,
    _mime_for,
    _read_image_local,
    _read_image_url,
    execute_shell,
    get_all_tools,
    list_dir,
    read_file,
    read_image,
    reload_tools,
)
from focus.tools.helpers import build_tool_result


class TestExecuteShell:
    def test_timeout_clamped(self, monkeypatch):
        captured = {}

        class FakeResult:
            stdout = "out"
            stderr = ""
            returncode = 0

        def fake_run(cmd, **kwargs):
            captured["timeout"] = kwargs["timeout"]
            return FakeResult()

        monkeypatch.setattr("focus.tools.builtin.subprocess.run", fake_run)
        execute_shell("echo hi", timeout_s=99999)
        assert captured["timeout"] == _MAX_SHELL_TIMEOUT

    def test_timeout_floor(self, monkeypatch):
        captured = {}

        class FakeResult:
            stdout = ""
            stderr = ""
            returncode = 0

        def fake_run(cmd, **kwargs):
            captured["timeout"] = kwargs["timeout"]
            return FakeResult()

        monkeypatch.setattr("focus.tools.builtin.subprocess.run", fake_run)
        execute_shell("echo hi", timeout_s=-5)
        assert captured["timeout"] == 1

    def test_default_timeout_used(self, monkeypatch):
        captured = {}

        class FakeResult:
            stdout = ""
            stderr = ""
            returncode = 0

        def fake_run(cmd, **kwargs):
            captured["timeout"] = kwargs["timeout"]
            return FakeResult()

        monkeypatch.setattr("focus.tools.builtin.subprocess.run", fake_run)
        execute_shell("echo hi")
        assert captured["timeout"] == 10


class TestReadFile:
    def test_truncated_at_char_limit(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text("x" * 100_000)
        out = read_file(str(f))
        assert len(out) <= 32000

    def test_lines_limit(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("\n".join(f"line {i}" for i in range(100)))
        out = read_file(str(f), lines=5)
        assert out.count("\n") == 5
        assert out.startswith("line 0")

    def test_lines_zero_returns_empty(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("hello\nworld\n")
        assert read_file(str(f), lines=0) == ""

    def test_negative_lines_rejected(self, tmp_path):
        f = tmp_path / "lines.txt"
        f.write_text("hello")
        with pytest.raises(ValueError):
            read_file(str(f), lines=-1)

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_file(str(tmp_path / "nope.txt"))

    def test_exact_limit_returns_full(self, tmp_path):
        f = tmp_path / "exact.txt"
        f.write_text("y" * 32000)
        assert len(read_file(str(f))) == 32000

    def test_directory_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="Not a file"):
            read_file(str(tmp_path))


class TestListDir:
    def test_lists_entries_sorted(self, tmp_path):
        (tmp_path / "b.txt").write_text("x")
        (tmp_path / "a").mkdir()
        out = list_dir(str(tmp_path))
        assert out.split("\n") == ["a\tdir", "b.txt\tfile"]

    def test_empty_dir(self, tmp_path):
        assert list_dir(str(tmp_path)) == "(empty directory)"

    def test_missing_dir_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            list_dir(str(tmp_path / "nope"))


class TestReadImageLocal:
    def test_success(self, tmp_path):
        buf = BytesIO()
        Image.new("RGB", (4, 4)).save(buf, format="PNG")
        path = tmp_path / "img.png"
        path.write_bytes(buf.getvalue())
        out = _read_image_local(str(path))
        assert out["image"]["mime"] == "image/png"
        assert base64.b64decode(out["image"]["base64"]) == buf.getvalue()
        assert out["image"]["path"] == str(path)

    def test_missing(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _read_image_local(str(tmp_path / "nope.png"))


class TestMimeFor:
    def test_content_type_wins(self):
        assert _mime_for("x.bin", "image/png; charset=utf-8") == "image/png"

    def test_guess_from_path(self):
        assert _mime_for("x.jpg") == "image/jpeg"

    def test_fallback_png(self):
        assert _mime_for("x.unknown") == "image/png"


class TestExecuteShellOutput:
    def test_stderr_appended(self):
        out = execute_shell("echo out; echo err >&2")
        assert out.startswith("out")
        assert "[stderr]\nerr" in out

    def test_non_zero_exit_with_empty_output(self):
        assert execute_shell("exit 7") == "(exit code 7)"


class _FakeUrlResp:
    def __init__(self, data, content_type="image/png"):
        self.data = data
        self.headers = {"Content-Type": content_type}

    def read(self, n):
        return self.data

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TestReadImageUrl:
    def test_success(self, monkeypatch):
        raw = b"\x89PNG fake-image"
        opener = type("Opener", (), {"open": lambda self, req, timeout=30: _FakeUrlResp(raw)})()
        monkeypatch.setattr("focus.tools.builtin.build_opener", lambda *a, **k: opener)
        out = _read_image_url("https://8.8.8.8/x.png")
        assert out["image"]["mime"] == "image/png"
        assert base64.b64decode(out["image"]["base64"]) == raw

    def test_oversize_rejected(self, monkeypatch):
        opener = type("Opener", (), {"open": lambda self, req, timeout=30: _FakeUrlResp(b"x" * 100)})()
        monkeypatch.setattr("focus.tools.builtin.build_opener", lambda *a, **k: opener)
        monkeypatch.setattr("focus.tools.builtin._MAX_URL_FETCH_BYTES", 8)
        with pytest.raises(RuntimeError, match="too large"):
            _read_image_url("https://8.8.8.8/x.png")

    def test_fetch_error_wrapped(self, monkeypatch):
        def bad_opener(*a, **k):
            raise OSError("connection refused")

        monkeypatch.setattr("focus.tools.builtin.build_opener", bad_opener)
        with pytest.raises(RuntimeError, match="Failed to fetch"):
            _read_image_url("https://8.8.8.8/x.png")

    def test_redirect_rechecks_safety(self, monkeypatch):
        from urllib.request import Request

        from focus.tools.builtin import _SafeRedirectHandler

        checked = []
        monkeypatch.setattr("focus.tools.builtin._check_url_safe", lambda url: checked.append(url))
        req = Request("https://example.com/start")
        handler = _SafeRedirectHandler()
        new_req = handler.redirect_request(req, None, 302, "moved", {}, "https://8.8.8.8/target")
        assert new_req is not None
        assert checked == ["https://8.8.8.8/target"]


class TestToolRegistry:
    def test_get_all_tools_includes_builtins(self):
        names = {t.name for t in get_all_tools()}
        assert {"read_file", "list_dir", "read_image", "execute_shell"} <= names

    def test_reload_tools_returns_list(self):
        tools = reload_tools()
        assert isinstance(tools, list)
        assert any(t.name == "read_file" for t in tools)


class TestCheckUrlSafe:
    @pytest.mark.parametrize("url", [
        "http://127.0.0.1:8080/x",
        "http://localhost/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/",
        "http://192.168.1.1/",
        "http://172.16.0.1/",
        "http://0.0.0.0/",
        "http://[::1]/",
        "file:///etc/passwd",
        "ftp://example.com/x",
    ])
    def test_blocks_non_global_targets(self, url):
        with pytest.raises(RuntimeError):
            _check_url_safe(url)

    @pytest.mark.parametrize("url", [
        "http://8.8.8.8/x",
        "https://1.1.1.1/",
        "http://93.184.216.34/",
    ])
    def test_allows_public_targets(self, url):
        _check_url_safe(url)

    def test_no_host_rejected(self):
        with pytest.raises(RuntimeError, match="no host"):
            _check_url_safe("http:///x")

    def test_dns_failure_rejected(self, monkeypatch):
        def fail(host, port=None):
            raise OSError("no such host")

        monkeypatch.setattr("focus.tools.builtin.socket.getaddrinfo", fail)
        with pytest.raises(RuntimeError, match="Could not resolve"):
            _check_url_safe("http://does-not-exist.example/x")

    def test_unparsable_address_rejected(self, monkeypatch):
        monkeypatch.setattr(
            "focus.tools.builtin.socket.getaddrinfo",
            lambda host, port=None: [((2, 1, 6, "", ("not-an-ip", 0)))],
        )
        with pytest.raises(RuntimeError, match="Unparsable"):
            _check_url_safe("http://weird.example/x")


class TestReadImageScheme:
    def test_url_scheme_case_insensitive(self, monkeypatch):
        called = {}

        def fake(url):
            called["url"] = url
            return {}

        monkeypatch.setattr("focus.tools.builtin._read_image_url", fake)
        read_image("HTTP://8.8.8.8/x.png")
        assert called["url"] == "HTTP://8.8.8.8/x.png"

    def test_missing_local_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_image(str(tmp_path / "missing.png"))


class TestBuildToolResult:
    async def test_converts_image_to_current_format(self):
        buf = BytesIO()
        Image.new("RGBA", (32, 32), (0, 255, 0, 200)).save(buf, format="WEBP")
        raw = buf.getvalue()
        b64 = base64.b64encode(raw).decode()
        output = {"image": {"base64": b64, "mime": "image/webp", "path": "x.png"}}
        set_image_format("jpeg")
        try:
            result = await build_tool_result("call1", "read_image", output, multimodal=True)
        finally:
            set_image_format("webp")
        assert not result.is_error
        assert result.image_data_url == f"data:image/webp;base64,{b64}"
        parts = result.extra_message["content"]
        url = parts[1]["image_url"]["url"]
        assert url.startswith("data:image/jpeg;base64,")
        img = Image.open(BytesIO(base64.b64decode(url.split(",", 1)[1])))
        assert img.mode == "RGB"
        assert "32x32" in result.content

    async def test_invalid_base64_is_error(self):
        result = await build_tool_result("c1", "t", {"image": {"base64": "!!!"}}, multimodal=True)
        assert result.is_error

    async def test_corrupt_image_is_error(self):
        b64 = base64.b64encode(b"not an image").decode()
        result = await build_tool_result("c1", "t", {"image": {"base64": b64}}, multimodal=True)
        assert result.is_error

    async def test_non_multimodal_image_returns_text(self):
        b64 = base64.b64encode(b"AAAA").decode()
        result = await build_tool_result("c1", "t", {"image": {"base64": b64}}, multimodal=False)
        assert result.extra_message is None
        assert not result.is_error
