from pipeline.stages import BRStage, LRTStage, AEStage, PRStage, default_stages


def test_default_stages_order():
    names = [s.name for s in default_stages()]
    assert names == ["BR", "LRT", "AE", "PR"]


def test_lrt_stage_is_manual():
    assert LRTStage().manual is True
    assert BRStage().manual is False


def test_br_stage_emits_progress():
    messages = []
    BRStage().run(config=None, emit=messages.append)
    assert any("BR" in m for m in messages)


def test_ae_and_pr_stages_emit_progress():
    msgs = []
    AEStage().run(config=None, emit=msgs.append)
    PRStage().run(config=None, emit=msgs.append)
    assert any("AE" in m for m in msgs)
    assert any("PR" in m for m in msgs)
