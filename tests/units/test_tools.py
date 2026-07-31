"""Unit tests for tool runtime limits and URL safety (focus/tools/builtin.py)."""

from pathlib import Path

import pytest

from focus.tools.builtin import (
    _MAX_SHELL_TIMEOUT,
    _check_url_safe,
    execute_shell,
    read_file,
    read_image,
)


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
