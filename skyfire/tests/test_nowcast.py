import pytest

from skyfire.nowcast import FusedScore, fuse, obs_score, obs_weight


def test_obs_weight_curve():
    assert obs_weight(400) == pytest.approx(0.3)     # T-6h 之外封顶 0.3
    assert obs_weight(360) == pytest.approx(0.3)
    assert obs_weight(240) == pytest.approx(0.45)    # 线性上升
    assert obs_weight(120) == pytest.approx(0.6)
    assert obs_weight(60) == pytest.approx(0.85)     # T-1h 起实况主导
    assert obs_weight(10) == pytest.approx(0.85)


def test_obs_score_canvas_and_corridor():
    good = obs_score(local_cloudiness=50, corridor_pred=[10, 15, 5, 20])
    bad_blocked = obs_score(local_cloudiness=50, corridor_pred=[90, 95, 92, 88])
    bad_clear = obs_score(local_cloudiness=2, corridor_pred=[10, 5, 5, 10])
    assert good >= 7.0
    assert bad_blocked <= 2.5
    assert bad_clear <= 2.0


def test_fuse_weights_and_degrade():
    r = fuse(rule_score=8.0, observed=2.0, minutes_to_window=60, frame_age_min=20)
    assert r.score == pytest.approx(8.0 * 0.15 + 2.0 * 0.85, abs=0.05)
    assert not r.degraded
    stale = fuse(rule_score=8.0, observed=2.0, minutes_to_window=60, frame_age_min=45)
    assert stale.degraded and stale.score == 8.0  # 帧龄超 40 分钟:不拿旧图冒充实况(spec 5.4)
