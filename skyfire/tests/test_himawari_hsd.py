# tests/test_himawari_hsd.py
import bz2
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

import skyfire.himawari_hsd as hsd_mod
from skyfire.himawari_hsd import (
    BAND_RES, CROP_BBOX, bucket_for, case_frame_times, download_segments,
    fetch_case_frames, hsd_key, sat_code, segments_for, v_fraction,
)
from skyfire.himawari_hsd import latest_slot


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


def test_latest_slot_scans_back_until_found():
    ok_ts = {"20260704_1340"}

    def handler(request: httpx.Request) -> httpx.Response:
        if any(k in str(request.url) for k in ok_ts):
            return httpx.Response(200, content=bz2.compress(b"D"))
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    now = datetime(2026, 7, 4, 14, 5, tzinfo=timezone.utc)
    ts = latest_slot(client, now, max_back=8)
    assert ts == datetime(2026, 7, 4, 13, 40, tzinfo=timezone.utc)


def test_latest_slot_none_when_nothing_recent():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(404)))
    now = datetime(2026, 7, 4, 14, 5, tzinfo=timezone.utc)
    assert latest_slot(client, now, max_back=3) is None


def test_case_frame_times_sunset_ir_after_vis_before():
    peak = datetime(2026, 5, 6, 11, 13, tzinfo=timezone.utc)
    times = case_frame_times(peak, "sunset_glow")
    base = datetime(2026, 5, 6, 11, 10, tzinfo=timezone.utc)
    ir = [t for t, ch in times if ch == "ir"]
    vis = [t for t, ch in times if ch == "vis"]
    assert len(ir) == 4 and len(vis) == 2
    assert all(t >= base for t in ir)
    assert all(t <= base for t in vis)
    assert all(t.minute % 10 == 0 for t, _ in times)
    assert max(ir) == base + timedelta(minutes=30)


def test_case_frame_times_sunrise_mirrored():
    peak = datetime(2026, 1, 7, 23, 30, tzinfo=timezone.utc)
    times = case_frame_times(peak, "sunrise_glow")
    base = datetime(2026, 1, 7, 23, 30, tzinfo=timezone.utc)
    ir = [t for t, ch in times if ch == "ir"]
    vis = [t for t, ch in times if ch == "vis"]
    assert all(t <= base for t in ir)
    assert all(t >= base for t in vis)
    assert min(ir) == base - timedelta(minutes=30)


def test_fetch_case_frames_orchestration(tmp_path, monkeypatch):
    calls = {"download": [], "render": []}

    def fake_download(client, ts, band, segments, cache_dir):
        calls["download"].append((ts, band, tuple(segments)))
        if band == "B03" and ts.hour == 10 and ts.minute == 0:  # 模拟单帧缺档
            return []
        return [Path(f"seg_{band}_{ts:%H%M}.DAT")]

    def fake_render(dat_paths, band, bbox, out_png, *, lat, lon,
                    azimuth_deg, max_px=1400):
        calls["render"].append((band, str(out_png), lat, lon, azimuth_deg))
        Path(out_png).parent.mkdir(parents=True, exist_ok=True)
        Path(out_png).write_bytes(b"png")
        return Path(out_png)

    monkeypatch.setattr(hsd_mod, "download_segments", fake_download)
    monkeypatch.setattr(hsd_mod, "render_annotated", fake_render)

    peak = datetime(2026, 5, 6, 10, 47, tzinfo=timezone.utc)
    frames = fetch_case_frames(object(), peak, tmp_path,
                               prefix="beijing_2026-05-06_sunset_glow",
                               event="sunset_glow", lat=39.9, lon=116.4,
                               azimuth_deg=292.6)
    # ir 4 帧全出;vis 应 2 帧,其中 10:00(peak-40min)的缺档被跳过 → 共 5
    assert len(frames) == 5
    bands = [b for _, b, _ in frames]
    assert bands.count("ir") == 4 and bands.count("vis") == 1
    ts0, _, p0 = frames[0]
    assert ts0.minute % 10 == 0                       # 槽对齐
    assert p0.name.startswith("beijing_2026-05-06_sunset_glow_")
    # 段选择来自 CROP_BBOX(段 2)
    assert calls["download"][0][2] == (2,)
    # 方位角随每帧透传给渲染
    assert all(azimuth == 292.6 for *_, azimuth in calls["render"])
