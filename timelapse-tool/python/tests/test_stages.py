from types import SimpleNamespace

import pytest

from pipeline.stages import BRStage, LRTStage, AEStage, ExportStage, default_stages


def test_default_stages_order():
    names = [s.name for s in default_stages()]
    assert names == ["BR", "LRT", "AE", "导出"]


def test_br_and_lrt_are_manual():
    assert BRStage().manual is True
    assert LRTStage().manual is True
    assert AEStage().manual is False
    assert ExportStage().manual is False


def test_br_stage_emits_progress():
    messages = []
    cfg = SimpleNamespace(raw_folder="/tmp/raw")
    BRStage().run(cfg, emit=messages.append)
    assert any("BR" in m for m in messages)


def test_lrt_validate_resume_is_noop():
    LRTStage().validate_resume(config=None)  # LRT 无需导出，继续无前置校验


def test_br_validate_resume_is_noop():
    BRStage().validate_resume(config=None)  # 不抛异常


def test_ae_stage_renders_then_merges(monkeypatch, tmp_path):
    from pipeline import ae
    called = {}

    def fake_render(seq_folder, output_dir, fps, resolution, stabilize, emit, **kwargs):
        called["seq"] = seq_folder
        called["out"] = output_dir
        called["fps"] = fps
        called["resolution"] = resolution
        called["stabilize"] = stabilize
        emit("AE done")
        return ["/c/chunk_000.mov", "/c/chunk_001.mov"]

    def fake_merge(chunk_files, output_dir, emit, **kwargs):
        called["chunks"] = chunk_files
        called["merge_out"] = output_dir
        emit("merged")
        return ae.intermediate_path(output_dir)

    monkeypatch.setattr(ae, "render_sequence", fake_render)
    monkeypatch.setattr(ae, "merge_chunks", fake_merge)

    class Cfg:
        raw_folder = str(tmp_path / "raw")
        output_path = str(tmp_path / "out")
        fps = 30
        resolution = [3840, 2160]
        stabilize = {"enabled": False}

    msgs = []
    AEStage().run(Cfg(), msgs.append)
    assert called["seq"] == str(tmp_path / "raw")
    assert called["fps"] == 30
    assert called["stabilize"] == {"enabled": False}
    # 渲染产出的分块被原样交给合并，输出目录一致
    assert called["chunks"] == ["/c/chunk_000.mov", "/c/chunk_001.mov"]
    assert called["merge_out"] == str(tmp_path / "out")
    assert any("AE" in m for m in msgs)


def test_export_stage_delegates(monkeypatch, tmp_path):
    from pipeline import ae, export
    called = {}

    def fake_render(intermediate_video, output_dir, social, emit, **kwargs):
        called["inter"] = intermediate_video
        called["out"] = output_dir
        called["social"] = social
        emit("导出 done")
        return (export.master_path(output_dir), tmp_path / "s.mp4")

    monkeypatch.setattr(export, "render_exports", fake_render)

    class Cfg:
        output_path = str(tmp_path / "out")
        social = {"format": "H.265", "aspect": "9:16", "resolution": "1080p"}

    msgs = []
    ExportStage().run(Cfg(), msgs.append)
    assert called["inter"] == str(ae.intermediate_path(str(tmp_path / "out")))
    assert called["social"]["aspect"] == "9:16"
    assert any("导出" in m for m in msgs)
