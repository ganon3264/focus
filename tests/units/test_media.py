"""Unit tests for the unified image pipeline (focus/core/media.py)."""

import base64
from io import BytesIO

from PIL import Image

from focus.core import paths
from focus.core.media import (
    MAX_IMAGE_B64,
    MAX_IMAGE_DIMENSION,
    compress_image,
    get_compressed_image,
    persist_tool_image,
    set_image_format,
    tool_image_data_url,
)


def _rgba_png(size=(64, 64)) -> bytes:
    buf = BytesIO()
    Image.new("RGBA", size, (255, 0, 0, 128)).save(buf, format="PNG")
    return buf.getvalue()


def _open(data: bytes) -> Image.Image:
    return Image.open(BytesIO(data))


class TestCompressImage:
    def test_rgba_png_to_jpeg(self):
        out = compress_image(_rgba_png(), "jpeg")
        assert _open(out).mode == "RGB"

    def test_webp_to_jpeg_without_mime_hint(self):
        buf = BytesIO()
        Image.new("RGB", (16, 16), (10, 20, 30)).save(buf, format="WEBP")
        out = compress_image(buf.getvalue(), "jpeg")
        assert _open(out).format == "JPEG"

    def test_alpha_kept_for_webp(self):
        out = compress_image(_rgba_png(), "webp")
        img = _open(out)
        assert img.format == "WEBP"
        assert img.mode == "RGBA"

    def test_alpha_kept_for_png(self):
        out = compress_image(_rgba_png(), "png")
        assert _open(out).mode == "RGBA"

    def test_dimension_cap(self):
        out = compress_image(_rgba_png((3000, 1000)), "png")
        img = _open(out)
        assert max(img.width, img.height) <= MAX_IMAGE_DIMENSION

    def test_size_budget_respected(self):
        buf = BytesIO()
        Image.effect_noise((4000, 4000), 128).save(buf, format="PNG")
        out = compress_image(buf.getvalue(), "webp")
        b64_len = len(base64.b64encode(out).decode())
        assert b64_len <= MAX_IMAGE_B64

    def test_invalid_format_falls_back_to_webp(self):
        out = compress_image(_rgba_png(), "gif")
        assert _open(out).format == "WEBP"


class TestPersistToolImage:
    def test_stores_raw_bytes(self):
        raw = _rgba_png()
        url = f"data:image/png;base64,{base64.b64encode(raw).decode()}"
        rel = persist_tool_image(url)
        assert rel.startswith("tool/")
        assert rel.endswith(".png")
        stored = (paths.ASSETS_DIR / rel).read_bytes()
        assert stored == raw

    def test_non_data_url_returns_none(self):
        assert persist_tool_image("http://x/y.png") is None

    def test_jpeg_mime_gets_jpeg_ext(self):
        raw = b"junk"
        url = f"data:image/jpeg;base64,{base64.b64encode(raw).decode()}"
        rel = persist_tool_image(url)
        assert rel.endswith(".jpeg")


class TestGetCompressedImage:
    @staticmethod
    def _write_orig(rel: str, data: bytes):
        p = paths.ASSETS_DIR / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
        return p

    def test_creates_cache_and_reuses(self):
        orig_rel = "tool/testimg.png"
        self._write_orig(orig_rel, _rgba_png())
        data1, mime1 = get_compressed_image(orig_rel, "webp")
        assert mime1 == "image/webp"
        cache = paths.COMPRESSED_DIR / "tool" / "testimg.webp"
        assert cache.exists()
        mtime = cache.stat().st_mtime
        data2, mime2 = get_compressed_image(orig_rel, "webp")
        assert cache.stat().st_mtime == mtime
        assert data2 == data1
        assert mime2 == mime1

    def test_format_change_creates_second_cache_file(self):
        self._write_orig("tool/fmt.png", _rgba_png())
        get_compressed_image("tool/fmt.png", "webp")
        get_compressed_image("tool/fmt.png", "jpeg")
        assert (paths.COMPRESSED_DIR / "tool" / "fmt.webp").exists()
        assert (paths.COMPRESSED_DIR / "tool" / "fmt.jpg").exists()

    def test_recompresses_when_original_replaced(self):
        import time

        orig_rel = "tool/stale.png"
        p = self._write_orig(orig_rel, _rgba_png())
        get_compressed_image(orig_rel, "webp")
        cache = paths.COMPRESSED_DIR / "tool" / "stale.webp"
        assert cache.exists()
        time.sleep(0.01)
        p.write_bytes(_rgba_png((32, 32)))
        get_compressed_image(orig_rel, "webp")
        img = _open(cache.read_bytes())
        assert max(img.width, img.height) == 32

    def test_missing_original_returns_none(self):
        assert get_compressed_image("tool/nope.png", "webp") is None

    def test_relative_and_absolute_references_resolve_same_file(self):
        p = paths.ATTACHMENTS_DIR / "both.png"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_rgba_png())
        data1, _ = get_compressed_image(str(p), "webp")
        data2, _ = get_compressed_image("attachments/both.png", "webp")
        assert data2 == data1


class TestToolImageDataUrl:
    async def test_roundtrip_to_current_format(self):
        raw = _rgba_png()
        url = f"data:image/png;base64,{base64.b64encode(raw).decode()}"
        rel = persist_tool_image(url)
        set_image_format("jpeg")
        try:
            out = await tool_image_data_url(rel)
        finally:
            set_image_format("webp")
        assert out.startswith("data:image/jpeg;base64,")
        img = _open(base64.b64decode(out.split(",", 1)[1]))
        assert img.mode == "RGB"
