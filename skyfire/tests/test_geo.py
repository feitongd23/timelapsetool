import math

from skyfire.geo import channel_points, destination


def test_destination_due_north_100km():
    lat, lon = destination(39.9, 116.4, bearing_deg=0, distance_km=100)
    assert abs(lat - (39.9 + 100 / 111.2)) < 0.05  # 北向 ~0.9°/100km
    assert abs(lon - 116.4) < 0.01


def test_channel_points_spacing_and_count():
    pts = channel_points(39.9, 116.4, azimuth_deg=302, start_km=50, end_km=400, step_km=50)
    assert len(pts) == 8  # 50,100,...,400
    assert pts[0].dist_km == 50 and pts[-1].dist_km == 400
    # 302° = 西北偏西,经度应递减、纬度递增
    assert pts[-1].lon < 116.4 and pts[-1].lat > 39.9
