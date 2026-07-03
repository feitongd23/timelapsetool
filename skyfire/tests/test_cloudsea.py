from skyfire.scoring.cloudsea import CloudSeaInputs, cloud_sea_score


def _inputs(**kw):
    base = dict(night_cloud_avg=10, dawn_rh=97, dawn_wind=1.5,
                dawn_temp_dew_spread=1.0, dawn_cloud_low=50)
    base.update(kw)
    return CloudSeaInputs(**base)


def test_ideal_radiation_fog_night_scores_high():
    assert cloud_sea_score(_inputs()).score >= 8.5


def test_windy_night_scores_low():
    assert cloud_sea_score(_inputs(dawn_wind=8.0)).score <= 6.0


def test_dry_air_scores_low():
    r = cloud_sea_score(_inputs(dawn_rh=60, dawn_temp_dew_spread=8, dawn_cloud_low=0))
    assert r.score <= 3.5


def test_overcast_night_blocks_radiation_cooling():
    ideal = cloud_sea_score(_inputs()).score
    cloudy = cloud_sea_score(_inputs(night_cloud_avg=90)).score
    assert cloudy <= ideal - 3.0
