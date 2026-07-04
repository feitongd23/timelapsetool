# tests/test_himawari_hsd.py
from datetime import datetime, timezone

from skyfire.himawari_hsd import (
    BAND_RES, CROP_BBOX, bucket_for, hsd_key, sat_code, segments_for, v_fraction,
)


def test_v_fraction_equator_center():
    assert abs(v_fraction(0.0, 140.7) - 0.5) < 0.002


def test_v_fraction_north_is_upper():
    assert v_fraction(40.0, 116.4) < v_fraction(36.0, 116.4) < 0.5


def test_beijing_crop_bbox_falls_in_segment_2():
    lon_min, lat_min, lon_max, lat_max = CROP_BBOX
    assert segments_for(lat_min, lat_max, (lon_min + lon_max) / 2) == [2]


def test_bucket_for_h9_h8_cutover():
    assert bucket_for(datetime(2023, 1, 1, tzinfo=timezone.utc)) == "noaa-himawari9"
    assert bucket_for(datetime(2021, 6, 18, tzinfo=timezone.utc)) == "noaa-himawari8"


def test_hsd_key_pattern():
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
    key = hsd_key(ts, "B13", 2, sat="H09")
    assert key == ("AHI-L1b-FLDK/2026/05/06/1000/"
                   "HS_H09_20260506_1000_B13_FLDK_R20_S0210.DAT.bz2")
    assert BAND_RES["B03"] == "R05"
    assert sat_code("noaa-himawari8") == "H08"


import bz2

import httpx

from skyfire.himawari_hsd import download_segments


def _mock_client(store: dict) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        store.setdefault("urls", []).append(str(request.url))
        if "noaa-himawari9" in str(request.url) and store.get("h9_404"):
            return httpx.Response(404)
        return httpx.Response(200, content=bz2.compress(b"FAKE_HSD_DATA"))
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_download_segments_decompresses_and_caches(tmp_path):
    store = {}
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
    paths = download_segments(_mock_client(store), ts, "B13", [2], tmp_path)
    assert len(paths) == 1
    assert paths[0].name == "HS_H09_20260506_1000_B13_FLDK_R20_S0210.DAT"
    assert paths[0].read_bytes() == b"FAKE_HSD_DATA"
    # 再次调用命中缓存,不再发请求
    n = len(store["urls"])
    download_segments(_mock_client(store), ts, "B13", [2], tmp_path)
    assert len(store["urls"]) == n


def test_download_segments_falls_back_to_other_bucket(tmp_path):
    store = {"h9_404": True}
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)  # 按日期主选 H9
    paths = download_segments(_mock_client(store), ts, "B13", [2], tmp_path)
    assert len(paths) == 1
    assert "noaa-himawari8" in store["urls"][-1]          # 回退到 H8
    assert paths[0].name.startswith("HS_H08_")


def test_download_segments_both_missing_returns_empty(tmp_path):
    def handler(request):
        return httpx.Response(404)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
    assert download_segments(client, ts, "B13", [2], tmp_path) == []
