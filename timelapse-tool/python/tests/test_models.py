import pytest

from pipeline.models import PipelineConfig, PipelineState


def _valid_kwargs(tmp_path):
    raw = tmp_path / "raw"; raw.mkdir()
    preset = tmp_path / "preset.xmp"; preset.write_text("x")
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    return dict(
        raw_folder=str(raw),
        camera_name="Sony A7R IV",
        acr_preset_path=str(preset),
        lrt_export_folder=str(lrt),
        stabilize=True,
        resolution=[3840, 2160],
        fps=24,
        codec="ProRes",
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
    kwargs["fps"] = 99
    with pytest.raises(ValueError, match="帧率"):
        PipelineConfig(**kwargs).validate()


def test_bad_codec_fails(tmp_path):
    kwargs = _valid_kwargs(tmp_path)
    kwargs["codec"] = "WMV"
    with pytest.raises(ValueError, match="编码"):
        PipelineConfig(**kwargs).validate()


def test_states_exist():
    assert PipelineState.IDLE
    assert PipelineState.RUNNING
    assert PipelineState.WAITING_FOR_USER
    assert PipelineState.DONE
    assert PipelineState.FAILED
