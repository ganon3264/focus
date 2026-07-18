import pytest

from pyvern.utils import (
    _image_dims_from_data_url,
    estimate_image_tokens,
    variable_group_name,
    SUFFIX_MIME_MAP,
    SUFFIX_MIME_MAP_IMAGES_ONLY,
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
    def test_small_image_both_under_384(self):
        assert estimate_image_tokens(200, 200) == 258

    def test_small_image_edge_384(self):
        assert estimate_image_tokens(384, 384) == 258

    def test_large_image(self):
        result = estimate_image_tokens(1024, 768)
        assert result == 258 * 2  # ceil(1024/768)=2 * ceil(768/768)=1 * 258

    def test_tall_image(self):
        result = estimate_image_tokens(300, 1600)
        assert result == 258 * 3  # ceil(300/768)=1 * ceil(1600/768)=3 * 258

    def test_very_large_image(self):
        result = estimate_image_tokens(2048, 2048)
        expected = 258 * 9  # ceil(2048/768)=3 * 3 * 258
        assert result == expected


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
