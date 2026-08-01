"""Unit tests for tool runtime limits and URL safety (focus/tools/builtin.py)."""

import base64
from io import BytesIO

import pytest
from PIL import Image

from focus.core.media import set_image_format
from focus.tools.builtin import (
    _MAX_SHELL_TIMEOUT,
    _check_url_safe,
    execute_shell,
    read_file,
    read_image,
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
