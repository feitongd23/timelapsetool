from skyfire.models import ChannelPoint
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score

CLEAN_CHANNEL = [ChannelPoint(dist_km=d, cloud_low=5, cloud_total=15) for d in range(50, 401, 50)]
BLOCKED_CHANNEL = [ChannelPoint(dist_km=d, cloud_low=90, cloud_total=95) for d in range(50, 401, 50)]


def _inputs(**kw):
    base = dict(cloud_high=50, cloud_mid=10, cloud_low=10,
                precipitation=0, aod=0.2, channel=CLEAN_CHANNEL)
    base.update(kw)
    return FireCloudInputs(**base)


def test_ideal_conditions_score_high():
    r = fire_cloud_score(_inputs())
    assert r.score >= 8.5


def test_clear_sky_scores_zero():
    r = fire_cloud_score(_inputs(cloud_high=0, cloud_mid=0))
    assert r.score == 0.0


def test_blocked_channel_is_veto():
    r = fire_cloud_score(_inputs(channel=BLOCKED_CHANNEL))
    assert r.score <= 1.5
    assert r.blocked_points == 7  # 100-400km 内 7 个点全堵


def test_local_overcast_low_cloud_penalized():
    r = fire_cloud_score(_inputs(cloud_low=95))
    assert r.score <= 3.0


def test_heavy_aerosol_penalized():
    clean = fire_cloud_score(_inputs(aod=0.2)).score
    hazy = fire_cloud_score(_inputs(aod=1.2)).score
    assert hazy < clean * 0.5


def test_rain_in_window_penalized():
    r = fire_cloud_score(_inputs(precipitation=2.0))
    assert r.score <= 2.5


def test_missing_aod_is_neutral():
    r = fire_cloud_score(_inputs(aod=None))
    assert r.score >= 8.5


HIGH_CANVAS_CHANNEL = [ChannelPoint(dist_km=d, cloud_low=8, cloud_total=100)
                       for d in range(50, 401, 50)]


def test_full_high_cloud_sheet_is_best_canvas_not_overcast():
    # 2026-07-07 漏报根因#1:EC/ICON 高云100%(实际被染透的云幕)曾被归零
    r = fire_cloud_score(_inputs(cloud_high=100, cloud_mid=0, cloud_low=9))
    assert r.canvas == 10.0
    assert r.score >= 8.0


def test_overcast_with_thick_mid_low_still_penalized():
    # 中低云主导的闷盖仍要压分
    r = fire_cloud_score(_inputs(cloud_high=60, cloud_mid=60, cloud_low=60))
    assert r.canvas <= 4.0


def test_channel_ignores_high_cloud_cover():
    # 根因#2:通道点 total=100 但 low 仅8%(纯高云盖顶)不算堵
    r = fire_cloud_score(_inputs(cloud_high=50, cloud_mid=10,
                                 channel=HIGH_CANVAS_CHANNEL))
    assert r.blocked_points == 0
    assert r.channel_factor == 1.0


def test_channel_low_cloud_still_blocks():
    r = fire_cloud_score(_inputs(channel=BLOCKED_CHANNEL))
    assert r.channel_factor == 0.1
