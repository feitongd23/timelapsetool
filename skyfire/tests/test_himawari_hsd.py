# tests/test_himawari_hsd.py
import bz2
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

import skyfire.himawari_hsd as hsd_mod
from skyfire.himawari_hsd import (
    BAND_RES, CROP_BBOX, bucket_for, download_segments, fetch_case_frames,
    hsd_key, sat_code, segments_for, v_fraction,
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


def test_download_segments_raises_on_server_error(tmp_path):
    # 非 404(如 5xx)不是"该桶无档",不换桶、不吞错,直接抛
    def handler(request):
        return httpx.Response(500)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
    with pytest.raises(httpx.HTTPStatusError):
        download_segments(client, ts, "B13", [2], tmp_path)


def test_download_segments_multi_segment_partial_404_falls_back(tmp_path):
    # 主桶(H9)段2 有档、段3 404 → 整体回退 H8 重下全部段
    urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        urls.append(url)
        if "noaa-himawari9" in url and "S0310" in url:
            return httpx.Response(404)
        return httpx.Response(200, content=bz2.compress(b"FAKE_HSD_DATA"))

    client = httpx.Client(transport=httpx.MockTransport(handler))
    ts = datetime(2026, 5, 6, 10, 0, tzinfo=timezone.utc)
    paths = download_segments(client, ts, "B13", [2, 3], tmp_path)
    assert [p.name for p in paths] == [
        "HS_H08_20260506_1000_B13_FLDK_R20_S0210.DAT",
        "HS_H08_20260506_1000_B13_FLDK_R20_S0310.DAT",
    ]
    assert all(p.read_bytes() == b"FAKE_HSD_DATA" for p in paths)
    assert sum("noaa-himawari8" in u for u in urls) == 2   # H8 两段都重下
    # 主桶已成功的段留在缓存,不污染返回结果
    assert (tmp_path / "HS_H09_20260506_1000_B13_FLDK_R20_S0210.DAT").exists()


def test_fetch_case_frames_orchestration(tmp_path, monkeypatch):
    calls = {"download": [], "render": []}

    def fake_download(client, ts, band, segments, cache_dir):
        calls["download"].append((ts, band, tuple(segments)))
        if band == "B03" and ts.hour == 9 and ts.minute == 10:  # 模拟单帧缺档
            return []
        return [Path(f"seg_{band}_{ts:%H%M}.DAT")]

    def fake_render(dat_paths, band, bbox, out_png, max_px=1400):
        calls["render"].append((band, str(out_png)))
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        Path(out_png).write_bytes(b"png")
        return Path(out_png)

    monkeypatch.setattr(hsd_mod, "download_segments", fake_download)
    monkeypatch.setattr(hsd_mod, "render_band", fake_render)

    peak = datetime(2026, 5, 6, 10, 47, tzinfo=timezone.utc)
    frames = fetch_case_frames(object(), peak, tmp_path,
                               prefix="beijing_2026-05-06_sunset_glow")
    # ir 4 帧全出;vis 应 2 帧,其中 09:10(peak-90min)的缺档被跳过 → 共 5
    assert len(frames) == 5
    bands = [b for _, b, _ in frames]
    assert bands.count("ir") == 4 and bands.count("vis") == 1
    ts0, _, p0 = frames[0]
    assert ts0.minute % 10 == 0                       # 槽对齐
    assert p0.name.startswith("beijing_2026-05-06_sunset_glow_")
    # 段选择来自 CROP_BBOX(段 2)
    assert calls["download"][0][2] == (2,)
