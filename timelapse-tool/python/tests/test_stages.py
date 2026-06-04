from types import SimpleNamespace

import pytest

from pipeline.stages import BRStage, LRTStage, AEStage, PRStage, default_stages


def test_default_stages_order():
    names = [s.name for s in default_stages()]
    assert names == ["BR", "LRT", "AE", "PR"]


def test_br_and_lrt_are_manual():
    assert BRStage().manual is True
    assert LRTStage().manual is True
    assert AEStage().manual is False
    assert PRStage().manual is False


def test_br_stage_emits_progress():
    messages = []
    cfg = SimpleNamespace(raw_folder="/tmp/raw")
    BRStage().run(cfg, emit=messages.append)
    assert any("BR" in m for m in messages)


def test_lrt_validate_resume_is_noop():
    LRTStage().validate_resume(config=None)  # LRT 无需导出，继续无前置校验


def test_br_validate_resume_is_noop():
    BRStage().validate_resume(config=None)  # 不抛异常


def test_ae_stage_delegates_to_render(monkeypatch, tmp_path):
    from pipeline import ae
    called = {}

    def fake_render(seq_folder, output_dir, fps, stabilize, emit, **kwargs):
        called["seq"] = seq_folder
        called["out"] = output_dir
        called["fps"] = fps
        called["stabilize"] = stabilize
        emit("AE done")
        return ae.intermediate_path(output_dir)

    monkeypatch.setattr(ae, "render_sequence", fake_render)

    class Cfg:
        raw_folder = str(tmp_path / "raw")
        output_path = str(tmp_path / "out")
        fps = 30
        stabilize = {"enabled": False}

    msgs = []
    AEStage().run(Cfg(), msgs.append)
    assert called["seq"] == str(tmp_path / "raw")
    assert called["fps"] == 30
    assert called["stabilize"] == {"enabled": False}
    assert any("AE" in m for m in msgs)


def test_pr_stage_delegates_to_render(monkeypatch, tmp_path):
    from pipeline import pr
    called = {}

    def fake_render(intermediate_video, output_dir, export, emit, **kwargs):
        called["out"] = output_dir
        called["export"] = export
        emit("PR done")

    monkeypatch.setattr(pr, "render_final", fake_render)

    class Cfg:
        output_path = str(tmp_path / "out")
        export = {"codec": "ProRes", "container": "MOV", "prores_profile": "422 HQ"}

    msgs = []
    PRStage().run(Cfg(), msgs.append)
    assert called["out"] == str(tmp_path / "out")
    assert called["export"]["codec"] == "ProRes"
    assert any("PR" in m for m in msgs)
