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
    p_sweet, q_sweet = baseline_percent(6.0, "high", None, 50.0)
    assert q_sweet == 70                       # 甜区:质量 +10(云幕托底)
    assert p_sweet == 85                       # (60+10)*1.0 + 15
    p_none, q_none = baseline_percent(6.0, "high", None, 8.0)
    assert p_none == 20 and q_none == 20       # 没画布 → 双封顶 20
    p_full, q_full = baseline_percent(6.0, "high", None, 95.0)
    assert p_full == 20 and q_full == 45       # 满盖:质量×0.75,概率封顶


def test_cloud_thin_canvas_damps_quality():
    # 15-30%:画布偏薄,质量线性折减(0.6→1.0)
    _, q15 = baseline_percent(6.0, "high", None, 15.0)
    _, q25 = baseline_percent(6.0, "high", None, 25.0)
    assert q15 == 36 and q25 == 52             # 60*0.6 / 60*0.867
    _, q_no = baseline_percent(6.0, "high", None, None)
    assert q_no == 60                          # 缺云量不修正


def test_projected_beats_measured_and_bounds():
    # 外推值优先于实测;缺两者不加不减
    p, _ = baseline_percent(6.0, "high", 8.0, 50.0)
    assert p == 85                                            # 用外推 50(甜区)
    p2, q2 = baseline_percent(0.0, "degraded", None, None)
    assert p2 == 0 and q2 == 0
