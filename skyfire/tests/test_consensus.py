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


def test_median_resists_single_zeroed_model():
    # 2026-07-07 根因#4:均值曾被规则性零分拖垮(0.5/0.8/0/0 → 0.3)
    c = consensus({"ecmwf_ifs025": 4.9, "gfs_seamless": 8.5,
                   "icon_seamless": 6.8, "cma_grapes_global": 0.0})
    assert c.index == 5.8                      # median=(4.9+6.8)/2≈5.85,均值只有5.05
    assert c.confidence == "low"               # spread 8.5:真分歧要如实标低


def test_skill_weights_shift_index_toward_accurate_model():
    scores = {"ecmwf_ifs025": 8.0, "gfs_seamless": 2.0}
    equal = consensus(scores)
    weighted = consensus(scores, weights={"ecmwf_ifs025": 0.9,
                                          "gfs_seamless": 0.1})
    assert equal.index == 5.0
    assert weighted.index == 7.4               # 偏向历史更准的 EC


def test_partial_weights_fall_back_to_median():
    c = consensus({"ecmwf_ifs025": 8.0, "gfs_seamless": 2.0},
                  weights={"ecmwf_ifs025": 0.9})   # GFS 缺权重 → 不加权
    assert c.index == 5.0
