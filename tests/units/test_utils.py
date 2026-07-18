from focus.core.utils import (
    SUFFIX_MIME_MAP,
    SUFFIX_MIME_MAP_IMAGES_ONLY,
    _image_dims_from_data_url,
    estimate_image_tokens,
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
