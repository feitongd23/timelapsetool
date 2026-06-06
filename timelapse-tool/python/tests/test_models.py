import pytest

from pipeline.models import PipelineConfig, PipelineState


def _valid_kwargs(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    return dict(
        raw_folder=str(raw),
        camera_name="Sony A7R IV",
        stabilize={"enabled": True, "result": "smooth", "smoothness": 50, "method": "subspace"},
        resolution=[3840, 2160],
        fps=24,
        social={"format": "H.265", "aspect": "9:16", "resolution": "1080p"},
        output_path=str(out),
    )


def test_valid_config_passes(tmp_path):
    cfg = PipelineConfig(**_valid_kwargs(tmp_path))
    cfg.validate()


def test_missing_raw_folder_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["raw_folder"] = str(tmp_path / "nope")
    with pytest.raises(ValueError, match="RAW 文件夹"):
        PipelineConfig(**kwargs).validate()


def test_bad_fps_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["fps"] = 0
    with pytest.raises(ValueError, match="帧率"):
        PipelineConfig(**kwargs).validate()


def test_fps_above_range_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["fps"] = 240
    with pytest.raises(ValueError, match="帧率"):
        PipelineConfig(**kwargs).validate()


def test_custom_fps_in_range_passes(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["fps"] = 48  # 非预设但合法
    PipelineConfig(**kwargs).validate()


def test_bad_social_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["social"] = {"format": "AV1", "aspect": "9:16", "resolution": "1080p"}
    with pytest.raises(ValueError, match="格式"):
        PipelineConfig(**kwargs).validate()


def test_valid_h264_social_passes(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["social"] = {"format": "H.264", "aspect": "16:9", "resolution": "4K"}
    PipelineConfig(**kwargs).validate()


def test_bad_stabilize_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["stabilize"] = {"enabled": True, "result": "x", "smoothness": 50, "method": "subspace"}
    with pytest.raises(ValueError, match="结果"):
        PipelineConfig(**kwargs).validate()


def test_states_exist():
    assert PipelineState.IDLE
    assert PipelineState.RUNNING
    assert PipelineState.WAITING_FOR_USER
    assert PipelineState.DONE
    assert PipelineState.FAILED
