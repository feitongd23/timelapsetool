from skyfire.percent import baseline_percent


def test_quality_is_rule_times_ten_clamped():
    prob, qual = baseline_percent(4.2, "high", None, None)
    assert qual == 42
    _, q2 = baseline_percent(11.0, "high", None, None)
    assert q2 == 100


def test_confidence_scales_probability():
    p_high, _ = baseline_percent(6.0, "high", None, None)
    p_low, _ = baseline_percent(6.0, "low", None, None)
    assert p_high == 60 and p_low == 42        # 60*0.7


def test_cloud_sweet_zone_bonus_and_cap():
    p_sweet, _ = baseline_percent(6.0, "high", None, 50.0)   # 甜区 → +15
    assert p_sweet == 75
    p_none, _ = baseline_percent(6.0, "high", None, 8.0)     # 没画布 → 封顶 20
    assert p_none == 20
    p_full, _ = baseline_percent(6.0, "high", None, 95.0)    # 满盖 → 封顶 20
    assert p_full == 20


def test_projected_beats_measured_and_bounds():
    # 外推值优先于实测;缺两者不加不减
    p, _ = baseline_percent(6.0, "high", 8.0, 50.0)
    assert p == 75                                            # 用外推 50(甜区)
    p2, q2 = baseline_percent(0.0, "degraded", None, None)
    assert p2 == 0 and q2 == 0
