import pytest

from pipeline.models import PipelineConfig, PipelineState
from pipeline.runner import PipelineRunner
from pipeline.stages import Stage, LRTStage


def _cfg(tmp_path, with_seq_image=False):
    raw = tmp_path / "raw"; raw.mkdir()
    preset = tmp_path / "p.xmp"; preset.write_text("x")
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    if with_seq_image:
        (lrt / "0001.tif").write_text("img")
    return PipelineConfig(
        raw_folder=str(raw), camera_name="Cam", acr_preset_path=str(preset),
        lrt_export_folder=str(lrt), stabilize=False, resolution=[3840, 2160],
        fps=24, codec="ProRes", output_path=str(out),
    )


class RecordingStage(Stage):
    def __init__(self, name, manual=False):
        self.name = name
        self.manual = manual
        self.ran = False

    def run(self, config, emit):
        self.ran = True
        emit(f"{self.name} ran")


def test_start_pauses_at_manual_stage(tmp_path):
    stages = [RecordingStage("BR"), RecordingStage("LRT", manual=True),
              RecordingStage("AE"), RecordingStage("PR")]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path))
    assert runner.status()["state"] == PipelineState.WAITING_FOR_USER
    assert stages[0].ran is True
    assert stages[2].ran is False


def test_continue_requires_sequence_images(tmp_path):
    stages = [RecordingStage("LRT", manual=True), RecordingStage("AE")]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path, with_seq_image=False))
    with pytest.raises(ValueError, match="序列"):
        runner.continue_()


def test_continue_finishes_pipeline(tmp_path):
    stages = [RecordingStage("BR"), RecordingStage("LRT", manual=True),
              RecordingStage("AE"), RecordingStage("PR")]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path, with_seq_image=True))
    runner.continue_()
    assert runner.status()["state"] == PipelineState.DONE
    assert all(s.ran for s in stages)


def test_failure_sets_failed_state(tmp_path):
    class Boom(Stage):
        name = "AE"
        manual = False
        def run(self, config, emit):
            raise RuntimeError("炸了")

    stages = [RecordingStage("LRT", manual=True), Boom()]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path, with_seq_image=True))
    runner.continue_()
    st = runner.status()
    assert st["state"] == PipelineState.FAILED
    assert st["current_stage"] == "AE"
    assert "炸了" in st["error"]


def test_invalid_config_fails_fast(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.fps = 99
    runner = PipelineRunner(stages=[RecordingStage("BR")], emit=lambda m: None)
    with pytest.raises(ValueError, match="帧率"):
        runner.start(cfg)
