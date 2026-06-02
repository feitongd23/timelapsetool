import pytest

from pipeline.models import PipelineConfig, PipelineState


def _valid_kwargs(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    return dict(
        raw_folder=str(raw),
        camera_name="Sony A7R IV",
        lrt_export_folder=str(lrt),
        deflicker={"enabled": True, "strength": 50, "time_radius": 2},
        stabilize={"enabled": True, "result": "smooth", "smoothness": 50, "method": "subspace"},
        resolution=[3840, 2160],
        fps=24,
        export={"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"},
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


def test_bad_export_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["export"] = {"codec": "WMV", "container": "MP4"}
    with pytest.raises(ValueError, match="编码"):
        PipelineConfig(**kwargs).validate()


def test_valid_h265_export_passes(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["export"] = {"codec": "H.265", "container": "MP4", "bitrate_mbps": 60, "bit_depth": 10}
    PipelineConfig(**kwargs).validate()


def test_bad_stabilize_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["stabilize"] = {"enabled": True, "result": "x", "smoothness": 50, "method": "subspace"}
    with pytest.raises(ValueError, match="结果"):
        PipelineConfig(**kwargs).validate()


def test_bad_deflicker_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["deflicker"] = {"enabled": True, "strength": 999, "time_radius": 2}
    with pytest.raises(ValueError, match="去闪强度"):
        PipelineConfig(**kwargs).validate()


def test_states_exist():
    assert PipelineState.IDLE
    assert PipelineState.RUNNING
    assert PipelineState.WAITING_FOR_USER
    assert PipelineState.DONE
    assert PipelineState.FAILED
