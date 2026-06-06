import pytest

from pipeline.export_formats import (
    PRESETS,
    expand_preset,
    validate_export,
    container_for,
)


def test_presets_have_expected_names():
    assert "母版 · ProRes 422 HQ" in PRESETS
    assert "母版 · ProRes 4444" in PRESETS
    assert "交付 · H.265 10bit" in PRESETS
    assert "社媒 · H.264 高质量" in PRESETS
    assert "社媒 · H.264 压缩" in PRESETS


def test_expand_preset_returns_full_export_dict():
    exp = expand_preset("母版 · ProRes 422 HQ")
    assert exp["codec"] == "ProRes"
    assert exp["container"] == "MOV"
    assert exp["prores_profile"] == "422 HQ"


def test_expand_unknown_preset_raises():
    with pytest.raises(KeyError):
        expand_preset("不存在")


def test_container_for_codec():
    assert container_for("ProRes") == "MOV"
    assert container_for("H.264") == "MP4"
    assert container_for("H.265") == "MP4"


def test_validate_prores_ok():
    validate_export({"codec": "ProRes", "container": "MOV", "prores_profile": "4444"})


def test_validate_prores_bad_profile():
    with pytest.raises(ValueError, match="ProRes"):
        validate_export({"codec": "ProRes", "container": "MOV", "prores_profile": "999"})


def test_validate_h264_ok():
    validate_export({"codec": "H.264", "container": "MP4", "bitrate_mbps": 80, "quality": "high"})


def test_validate_h264_bad_bitrate():
    with pytest.raises(ValueError, match="码率"):
        validate_export({"codec": "H.264", "container": "MP4", "bitrate_mbps": 0, "quality": "high"})


def test_validate_h265_bad_bit_depth():
    with pytest.raises(ValueError, match="位深"):
        validate_export({"codec": "H.265", "container": "MP4", "bitrate_mbps": 60, "bit_depth": 12})


def test_validate_unknown_codec():
    with pytest.raises(ValueError, match="编码"):
        validate_export({"codec": "WMV", "container": "MP4"})


def test_validate_wrong_container_for_codec():
    with pytest.raises(ValueError, match="容器"):
        validate_export({"codec": "ProRes", "container": "MP4", "prores_profile": "422"})


from pipeline import export_formats as ef


def test_social_pixels_landscape_and_portrait():
    assert ef.social_pixels("16:9", "1080p") == (1920, 1080)
    assert ef.social_pixels("9:16", "1080p") == (1080, 1920)
    assert ef.social_pixels("3:4", "1080p") == (1080, 1440)
    assert ef.social_pixels("3:4", "720p") == (720, 960)
    assert ef.social_pixels("1:1", "1080p") == (1080, 1080)
    assert ef.social_pixels("3:2", "1080p") == (1620, 1080)
    assert ef.social_pixels("16:9", "4K") == (3840, 2160)


def test_social_pixels_always_even():
    for aspect in ef.ASPECT_RATIO:
        for res in ef.SOCIAL_RESOLUTIONS:
            w, h = ef.social_pixels(aspect, res)
            assert w % 2 == 0 and h % 2 == 0


def test_crop_rect_center_portrait_from_3to2():
    assert ef.crop_rect(3840, 2560, "9:16") == (1200, 0, 1440, 2560)


def test_crop_rect_center_landscape_169():
    assert ef.crop_rect(3840, 2560, "16:9") == (0, 200, 3840, 2160)


def test_crop_rect_square_and_34():
    assert ef.crop_rect(3840, 2560, "1:1") == (640, 0, 2560, 2560)
    assert ef.crop_rect(3840, 2560, "3:4") == (960, 0, 1920, 2560)


def test_crop_rect_native_3to2_is_full_frame():
    assert ef.crop_rect(3840, 2560, "3:2") == (0, 0, 3840, 2560)


def test_validate_social_ok_and_rejects():
    ef.validate_social({"format": "H.265", "aspect": "9:16", "resolution": "1080p"})
    with pytest.raises(ValueError, match="格式"):
        ef.validate_social({"format": "AV1", "aspect": "9:16", "resolution": "1080p"})
    with pytest.raises(ValueError, match="画幅"):
        ef.validate_social({"format": "H.265", "aspect": "21:9", "resolution": "1080p"})
    with pytest.raises(ValueError, match="分辨率"):
        ef.validate_social({"format": "H.265", "aspect": "9:16", "resolution": "8K"})
