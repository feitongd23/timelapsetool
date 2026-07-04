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


import io

import numpy as np
from PIL import Image

from skyfire.himawari import RegionFrame, fetch_region


def _png_bytes(value: int) -> bytes:
    img = Image.fromarray(np.full((550, 550), value, dtype=np.uint8), mode="L")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_fetch_region_stitches_grid_and_locates_center():
    def handler(request: httpx.Request) -> httpx.Response:
        # 用瓦片 x 坐标做灰度值,便于断言拼接顺序
        tx = int(request.url.path.rsplit("_", 2)[1])
        return httpx.Response(200, content=_png_bytes(tx * 40))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ts = datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)
    frame = fetch_region(client, "infrared", ts, 39.9042, 116.4074, level=8, grid=3)
    assert isinstance(frame, RegionFrame)
    assert frame.gray.shape == (3 * 550, 3 * 550)
    # 北京在 8d 的瓦片 (2, 1);3x3 网格起点 (1, 0)
    assert frame.origin_tile == (1, 0)
    # 左列灰度 40(tx=1)、中列 80(tx=2)、右列 120(tx=3)
    assert frame.gray[0, 0] == 40 and frame.gray[0, 800] == 80 and frame.gray[0, 1200] == 120
    # 中心像素应落在中间那块瓦片内
    cx, cy = frame.center_px
    assert 550 <= cx < 1100


def test_fetch_region_missing_tile_fills_zero():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ts = datetime(2026, 7, 4, 2, 10, 0, tzinfo=timezone.utc)
    frame = fetch_region(client, "infrared", ts, 39.9042, 116.4074, level=8, grid=3)
    assert frame.gray.max() == 0  # 全缺帧不抛异常,拼出全零图,由上层按帧龄/内容降级
