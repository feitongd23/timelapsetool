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
