import pytest

from pipeline.models import PipelineConfig, PipelineState
from pipeline.runner import PipelineRunner
from pipeline.stages import Stage, LRTStage


def _cfg(tmp_path, with_seq_image=False):
    raw = tmp_path / "raw"; raw.mkdir()
    lrt = tmp_path / "seq"; lrt.mkdir()
    out = tmp_path / "out"; out.mkdir()
    if with_seq_image:
        (lrt / "0001.tif").write_text("img")
    return PipelineConfig(
        raw_folder=str(raw), camera_name="Cam",
        stabilize={"enabled": False},
        resolution=[3840, 2160],
        fps=24, social={"format": "H.265", "aspect": "9:16", "resolution": "1080p"}, output_path=str(out),
    )


class RecordingStage(Stage):
    def __init__(self, name, manual=False):
        self.name = name
        self.manual = manual
        self.ran = False

    def run(self, config, emit):
        self.ran = True
        emit(f"{self.name} ran")


def test_start_pauses_at_first_manual_stage(tmp_path):
    stages = [RecordingStage("BR", manual=True), RecordingStage("AE")]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path))
    assert runner.status()["state"] == PipelineState.WAITING_FOR_USER
    assert runner.status()["current_stage"] == "BR"
    assert stages[1].ran is False  # AE 还没跑


def test_two_manual_stages_pause_twice(tmp_path):
    stages = [RecordingStage("BR", manual=True), RecordingStage("LRT", manual=True),
              RecordingStage("AE")]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path))
    assert runner.status()["current_stage"] == "BR"

    runner.continue_()  # 离开 BR，停在 LRT
    assert runner.status()["state"] == PipelineState.WAITING_FOR_USER
    assert runner.status()["current_stage"] == "LRT"
    assert "BR" in runner.status()["completed"]

    runner.continue_()  # 离开 LRT，跑完 AE
    assert runner.status()["state"] == PipelineState.DONE
    assert stages[2].ran is True


def test_lrt_resume_proceeds_without_export(tmp_path):
    # LRT 写 XMP 后无需导出序列，continue 直接推进（AE 直接吃 RAW）
    stages = [LRTStage(), RecordingStage("AE")]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path))
    runner.continue_()
    assert runner.status()["state"] == PipelineState.DONE


def test_manual_stage_without_resume_guard_continues(tmp_path):
    # BR（RecordingStage 默认 validate_resume 无校验）可直接继续，无需序列
    stages = [RecordingStage("BR", manual=True), RecordingStage("AE")]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path, with_seq_image=False))
    runner.continue_()
    assert runner.status()["state"] == PipelineState.DONE


def test_failure_sets_failed_state(tmp_path):
    class Boom(Stage):
        name = "AE"
        manual = False
        def run(self, config, emit):
            raise RuntimeError("炸了")

    stages = [RecordingStage("BR", manual=True), Boom()]
    runner = PipelineRunner(stages=stages, emit=lambda m: None)
    runner.start(_cfg(tmp_path))
    runner.continue_()
    st = runner.status()
    assert st["state"] == PipelineState.FAILED
    assert st["current_stage"] == "AE"
    assert "炸了" in st["error"]


def test_invalid_config_fails_fast(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.fps = 0
    runner = PipelineRunner(stages=[RecordingStage("BR", manual=True)], emit=lambda m: None)
    with pytest.raises(ValueError, match="帧率"):
        runner.start(cfg)
