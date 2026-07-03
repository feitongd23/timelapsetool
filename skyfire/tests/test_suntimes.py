from datetime import date

from skyfire.suntimes import sun_window


def test_beijing_summer_sunset():
    w = sun_window(39.9042, 116.4074, "Asia/Shanghai", date(2026, 6, 21), "sunset_glow")
    assert w.event == "sunset_glow"
    assert 19 <= w.peak.hour <= 20
    assert 290 <= w.azimuth_deg <= 315
    # 民用晨昏蒙影结束晚于日落
    assert w.window_end > w.peak


def test_beijing_summer_sunrise():
    w = sun_window(39.9042, 116.4074, "Asia/Shanghai", date(2026, 6, 21), "sunrise_glow")
    assert 4 <= w.peak.hour <= 6
    assert 45 <= w.azimuth_deg <= 70
    assert w.window_start < w.peak
