import pytest

from pipeline.effects import validate_deflicker, validate_stabilize, STABILIZE_METHODS


def test_deflicker_disabled_skips_param_checks():
    validate_deflicker({"enabled": False})  # 不抛


def test_deflicker_valid():
    validate_deflicker({"enabled": True, "strength": 50, "time_radius": 2})


def test_deflicker_bad_strength():
    with pytest.raises(ValueError, match="去闪强度"):
        validate_deflicker({"enabled": True, "strength": 200, "time_radius": 2})


def test_deflicker_bad_time_radius():
    with pytest.raises(ValueError, match="时间半径"):
        validate_deflicker({"enabled": True, "strength": 50, "time_radius": 0})


def test_stabilize_disabled_skips():
    validate_stabilize({"enabled": False})


def test_stabilize_valid():
    validate_stabilize({"enabled": True, "result": "smooth", "smoothness": 50, "method": "subspace"})


def test_stabilize_bad_result():
    with pytest.raises(ValueError, match="结果"):
        validate_stabilize({"enabled": True, "result": "x", "smoothness": 50, "method": "subspace"})


def test_stabilize_bad_method():
    with pytest.raises(ValueError, match="方法"):
        validate_stabilize({"enabled": True, "result": "smooth", "smoothness": 50, "method": "x"})


def test_stabilize_bad_smoothness():
    with pytest.raises(ValueError, match="平滑度"):
        validate_stabilize({"enabled": True, "result": "smooth", "smoothness": 999, "method": "subspace"})


def test_methods_constant():
    assert STABILIZE_METHODS == ["position", "pos_scale_rot", "perspective", "subspace"]
