from datetime import date, datetime

from skyfire.suntimes import nearest_iso_hour, sun_window


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


def test_nearest_iso_hour_keeps_hour_before_half():
    assert nearest_iso_hour(datetime(2026, 7, 6, 4, 29)) == "2026-07-06T04:00"


def test_nearest_iso_hour_rounds_up_from_half():
    # 修 bug:04:47 峰值此前被截断到 04:00 取数
    assert nearest_iso_hour(datetime(2026, 7, 6, 4, 47)) == "2026-07-06T05:00"


def test_nearest_iso_hour_crosses_midnight():
    assert nearest_iso_hour(datetime(2026, 7, 6, 23, 47)) == "2026-07-07T00:00"
