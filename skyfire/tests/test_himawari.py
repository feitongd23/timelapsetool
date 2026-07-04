from datetime import datetime, timezone

import httpx

from skyfire.himawari import (
    frame_age_minutes,
    latest_frame_time,
    lonlat_to_fraction,
    round_down_10min,
    tile_for,
    tile_url,
)


def test_lonlat_to_fraction_beijing():
    u, v = lonlat_to_fraction(39.9042, 116.4074)
    # 北京在 140.7°E 星下点西北方:图像左半(u<0.5)、上部(v<0.5)
    assert 0.30 <= u <= 0.38
    assert 0.14 <= v <= 0.22


def test_tile_for_beijing_level4():
    tx, ty = tile_for(39.9042, 116.4074, level=4)
    assert (tx, ty) == (1, 0)


def test_tile_url_pattern():
    ts = datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)
    url = tile_url("truecolor", ts, level=4, tx=1, ty=0)
    assert url == ("https://himawari8-dl.nict.go.jp/himawari8/img/"
                   "D531106/4d/550/2026/07/04/021000_1_0.png")
    ir = tile_url("infrared", ts, level=4, tx=1, ty=0)
    assert "/INFRARED_FULL/" in ir


def test_round_down_10min():
    ts = datetime(2026, 7, 4, 2, 17, 42, tzinfo=timezone.utc)
    assert round_down_10min(ts) == datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)


def test_latest_frame_time_parses_utc():
    def handler(request):
        return httpx.Response(200, json={"date": "2026-07-04 02:10:00",
                                         "file": "PI_H09_20260704_0210_TRC_FLDK_R10_PGPFD.png"})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    ts = latest_frame_time(client)
    assert ts == datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)


def test_frame_age_minutes():
    ts = datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)
    now = datetime(2026, 7, 4, 2, 45, 0, tzinfo=timezone.utc)
    assert frame_age_minutes(ts, now) == 35.0
