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
    BRStage().run(config=None, emit=messages.append)
    assert any("BR" in m for m in messages)


def test_lrt_validate_resume_requires_sequence(tmp_path):
    cfg = SimpleNamespace(lrt_export_folder=str(tmp_path))
    with pytest.raises(ValueError, match="序列"):
        LRTStage().validate_resume(cfg)
    (tmp_path / "0001.tif").write_text("img")
    LRTStage().validate_resume(cfg)  # 有图片后不抛


def test_br_validate_resume_is_noop():
    BRStage().validate_resume(config=None)  # 不抛异常


def test_ae_and_pr_stages_emit_progress():
    msgs = []
    AEStage().run(config=None, emit=msgs.append)
    PRStage().run(config=None, emit=msgs.append)
    assert any("AE" in m for m in msgs)
    assert any("PR" in m for m in msgs)
