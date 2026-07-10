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
    # 2026-07-11 F1:甜区改门控乘法(rule≥4 才享受,×1.10/×1.15)
    p_sweet, q_sweet = baseline_percent(6.0, "high", None, 50.0)
    assert q_sweet == 66                       # 60×1.10
    assert p_sweet == 76                       # 66×1.0×1.15
    p_none, q_none = baseline_percent(6.0, "high", None, 8.0)
    # 无云向零收敛(2026-07-11 采纳两家共识:烧不起来=白色底色)
    assert p_none == 11 and q_none == 11       # 20×8/15
    p_zero, q_zero = baseline_percent(6.0, "high", None, 0.0)
    assert p_zero == 0 and q_zero == 0         # 万里无云=0
    p_full, q_full = baseline_percent(6.0, "high", None, 95.0)
    assert p_full == 20 and q_full == 45       # 满盖:质量×0.75,概率封顶


def test_sweet_zone_cannot_resurrect_vetoed_score():
    """F1 核心:被硬门槛压死的分数禁止被甜区复活(今晚假色带头号根因)。"""
    p0, q0 = baseline_percent(0.0, "medium", None, 50.0)
    assert p0 == 0 and q0 == 0                 # 规则 0 → 双零,不再是 24/10
    p1, _ = baseline_percent(0.85, "medium", None, 50.0)
    assert p1 <= 10                            # 否决级(<1.0)概率钳制 10


def test_blocker_decoupled_from_canvas_full_cover():
    """F6:>90 封顶只看遮光云(中+低)——近西缘满盖卷云幕是经典大烧配置。"""
    # 画布云 100(满盖高云)但遮光云 10:不触发闷盖封顶
    p, q = baseline_percent(8.5, "medium", None, 100.0, blocker_cloud_pct=10.0)
    assert q == 85 and p > 20                  # 不被按在 20
    # 遮光云 95:照旧闷盖封顶
    p2, q2 = baseline_percent(8.5, "medium", None, 100.0, blocker_cloud_pct=95.0)
    assert p2 == 20 and q2 == 64               # 85×0.75


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
    assert p == 76                                            # 用外推 50(甜区,门控乘法)
    p2, q2 = baseline_percent(0.0, "degraded", None, None)
    assert p2 == 0 and q2 == 0
