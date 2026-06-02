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
