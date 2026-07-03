from skyfire.consensus import consensus


def test_agreement_gives_high_confidence():
    c = consensus({"ecmwf_ifs025": 7.8, "gfs_seamless": 7.2, "icon_seamless": 7.6, "cma_grapes_global": 6.9})
    assert c.confidence == "high"
    assert 7.0 <= c.index <= 7.6
    assert c.spread == 0.9


def test_disagreement_gives_low_confidence():
    c = consensus({"ecmwf_ifs025": 9.0, "gfs_seamless": 2.0})
    assert c.confidence == "low"


def test_single_model_is_degraded():
    c = consensus({"gfs_seamless": 6.0})
    assert c.index == 6.0
    assert c.confidence == "degraded"  # 单模式:数据不全,置信度降级(spec 8)
