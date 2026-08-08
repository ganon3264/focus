from io import BytesIO

import aiosqlite
import pytest
from starlette.datastructures import UploadFile

from focus.core.utils import (
    SUFFIX_MIME_MAP,
    SUFFIX_MIME_MAP_IMAGES_ONLY,
    TTLCache,
    _image_dims_from_data_url,
    estimate_image_tokens,
    greetings_from_card,
    parse_greetings_json,
    read_upload,
    resolve_secret_key,
    variable_group_name,
)


class TestVariableGroupName:
    def test_with_colon(self):
        assert variable_group_name("personality:positive") == "personality"

    def test_without_colon(self):
        assert variable_group_name("personality") == "personality"

    def test_multi_colon(self):
        assert variable_group_name("a:b:c") == "a"

    def test_empty_string(self):
        assert variable_group_name("") == ""


class TestEstimateImageTokens:
    def test_small_image_clamps_to_min(self):
        assert estimate_image_tokens(200, 200) == 250  # 40000//900=44 → clamp 250

    def test_edge_just_above_min(self):
        result = estimate_image_tokens(475, 475)
        assert result == 250  # 225625//900=250 → exactly min

    def test_medium_image(self):
        result = estimate_image_tokens(1024, 768)
        assert result == 873  # 786432//900=873

    def test_tall_image(self):
        result = estimate_image_tokens(300, 1600)
        assert result == 533  # 480000//900=533

    def test_very_large_image_scales_then_clamps_to_max(self):
        result = estimate_image_tokens(2048, 2048)
        # scaled to 2000×2000 → 4000000//900=4444 → clamp 1600
        assert result == 1600

    def test_downscaled_lands_between_clamps(self):
        result = estimate_image_tokens(3000, 600)
        # longest=3000, scale=2000/3000 ≈ 0.6667 → 2000×400 → 800000//900=888
        assert result == 888

    def test_very_tall_downscaled(self):
        result = estimate_image_tokens(400, 5000)
        # longest=5000, scale=2000/5000=0.4 → 160×2000 → 320000//900=355
        assert result == 355


class TestSuffixMimeMap:
    def test_standard_extensions(self):
        assert SUFFIX_MIME_MAP[".jpg"] == "image/jpeg"
        assert SUFFIX_MIME_MAP[".png"] == "image/png"
        assert SUFFIX_MIME_MAP[".mp3"] == "audio/mpeg"

    def test_images_only_filters_audio(self):
        assert ".mp3" not in SUFFIX_MIME_MAP_IMAGES_ONLY
        assert ".jpg" in SUFFIX_MIME_MAP_IMAGES_ONLY


class TestImageDimsFromDataUrl:
    def test_invalid_url_returns_none(self):
        assert _image_dims_from_data_url("not-a-url") is None

    def test_bad_base64_returns_none(self):
        assert _image_dims_from_data_url("data:,") is None

    def test_valid_image_returns_dims(self):
        import base64

        from PIL import Image

        buf = BytesIO()
        Image.new("RGB", (64, 32)).save(buf, format="PNG")
        url = f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"
        assert _image_dims_from_data_url(url) == (64, 32)


class TestParseGreetingsJson:
    def test_none_returns_none(self):
        assert parse_greetings_json(None) is None

    def test_valid_list(self):
        assert parse_greetings_json('["a", "b"]') == ["a", "b"]

    def test_malformed_returns_empty(self):
        assert parse_greetings_json("{nope") == []

    def test_non_list_returns_empty(self):
        assert parse_greetings_json('"just a string"') == []

    def test_filters_non_strings(self):
        assert parse_greetings_json('[1, "a", null]') == ["a"]


class TestGreetingsFromCard:
    def test_none_card(self):
        assert greetings_from_card(None) == []

    def test_first_mes_and_alts(self):
        card = {"first_mes": "Hi", "alternate_greetings": ["Yo", "Hey"]}
        assert greetings_from_card(card) == ["Hi", "Yo", "Hey"]

    def test_whitespace_filtered(self):
        card = {"first_mes": "  ", "alternate_greetings": ["ok", ""]}
        assert greetings_from_card(card) == ["ok"]


class TestTTLCache:
    async def test_get_miss_returns_none(self):
        cache = TTLCache()
        assert await cache.get("k") is None

    async def test_set_and_get(self):
        cache = TTLCache()
        await cache.set("k", "v")
        assert await cache.get("k") == "v"

    async def test_expiry(self, monkeypatch):
        import time as time_mod

        real_monotonic = time_mod.monotonic
        cache = TTLCache(ttl=10)
        await cache.set("k", "v")
        monkeypatch.setattr(time_mod, "monotonic", lambda: real_monotonic() + 11)
        assert await cache.get("k") is None

    async def test_get_or_refresh_caches(self):
        calls = []

        async def factory():
            calls.append(1)
            return "fresh"

        cache = TTLCache()
        assert await cache.get_or_refresh("k", factory) == "fresh"
        assert await cache.get_or_refresh("k", factory) == "fresh"
        assert len(calls) == 1

    async def test_get_or_refresh_null_factory_not_cached(self):
        cache = TTLCache()

        async def factory():
            return None

        assert await cache.get_or_refresh("k", factory) is None
        assert await cache.get("k") is None


class TestReadUpload:
    async def test_under_limit_returns_bytes(self):
        file = UploadFile(file=BytesIO(b"hello"))
        assert await read_upload(file) == b"hello"

    async def test_over_limit_raises_413(self, monkeypatch):
        import focus.core.utils as utils

        monkeypatch.setattr(utils, "MAX_UPLOAD_SIZE", 4)
        file = UploadFile(file=BytesIO(b"12345"))
        with pytest.raises(Exception) as exc:
            await read_upload(file)
        assert exc.type.__name__ == "HTTPException"
        assert exc.value.status_code == 413


class TestResolveSecretKey:
    async def test_plain_keys_passthrough(self, tmp_path):
        async with aiosqlite.connect(tmp_path / "t.db") as db:
            assert await resolve_secret_key(db, "plain") == "plain"
            assert await resolve_secret_key(db, "") == ""

    async def test_resolves_and_misses(self, tmp_path):
        async with aiosqlite.connect(tmp_path / "t.db") as db:
            db.row_factory = aiosqlite.Row
            await db.execute("CREATE TABLE secrets (name TEXT, value TEXT)")
            await db.execute("INSERT INTO secrets VALUES ('k1', 'v1')")
            await db.commit()
            assert await resolve_secret_key(db, "SECRET:k1") == "v1"
            assert await resolve_secret_key(db, "SECRET:missing") == ""

    async def test_db_error_returns_empty(self):
        class _BrokenDB:
            def execute(self, *a, **k):
                raise RuntimeError("boom")

        assert await resolve_secret_key(_BrokenDB(), "SECRET:x") == ""
