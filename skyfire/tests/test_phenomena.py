"""云海/彩虹引擎(phenomena):三道门与 L1-L3 配方的规则表口径。"""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from skyfire.phenomena import forecast_cloudsea, forecast_rainbow

TZ = "Asia/Shanghai"
LAT, LON = 39.9042, 116.4074


def _client(hourly_fn):
    def handler(request: httpx.Request) -> httpx.Response:
        lat = float(str(request.url.params["latitude"]))
        return httpx.Response(200, json={"hourly": hourly_fn(lat)})
    return httpx.Client(transport=httpx.MockTransport(handler))


def _series(days=("2026-07-10", "2026-07-11", "2026-07-12"), **overrides):
    times = [f"{d}T{h:02d}:00" for d in days for h in range(24)]
    n = len(times)
    base = {"time": times,
            "precipitation": [0.0] * n, "relative_humidity_2m": [60.0] * n,
            "wind_speed_10m": [2.0] * n, "temperature_2m": [25.0] * n,
            "dew_point_2m": [18.0] * n, "cloud_cover_low": [10.0] * n,
            "cloud_cover_mid": [10.0] * n, "cloud_cover_high": [20.0] * n,
            "boundary_layer_height": [500.0] * n, "visibility": [20000.0] * n}
    for var, pairs in overrides.items():
        for iso, v in pairs:
            base[var][times.index(iso)] = v
    return base


def _dawn_iso(day):
    from skyfire.suntimes import sun_window
    return sun_window(LAT, LON, TZ, day, "sunrise_glow").peak.strftime(
        "%Y-%m-%dT%H:00")


def test_cloudsea_full_match_2022_pattern():
    """2022-08-19 型满配:透雨+饱和静风+雾顶极低+上空无云 → 高概率景山档。"""
    day = date(2026, 7, 11)
    dawn = _dawn_iso(day)
    rain = [(f"2026-07-10T{h:02d}:00", 2.0) for h in range(10, 22)]  # 前日透雨24mm
    def hourly(lat):
        return _series(
            precipitation=rain,
            relative_humidity_2m=[(dawn, 97.0)], temperature_2m=[(dawn, 22.0)],
            dew_point_2m=[(dawn, 21.6)], wind_speed_10m=[(dawn, 1.5)],
            boundary_layer_height=[(dawn, 80.0)],
            cloud_cover_mid=[(dawn, 5.0)], cloud_cover_high=[(dawn, 10.0)])
    r = forecast_cloudsea(_client(hourly), LAT, LON, TZ, day)
    assert r["tier"] == "景山CBD档" and r["prob"] >= 80
    assert r["gates"]["成雾"] >= 1.0 and r["gates"]["有光"] == 1.0


def test_cloudsea_gates_are_multiplicative():
    """任一门为 0 → 概率 0(乘法门,不是加分制)。"""
    day = date(2026, 7, 11)
    dawn = _dawn_iso(day)
    def dry(lat):    # 干燥不成雾
        return _series(relative_humidity_2m=[(dawn, 55.0)])
    assert forecast_cloudsea(_client(dry), LAT, LON, TZ, day)["prob"] == 0
    def shaded(lat):  # 满配成雾但上空满盖 → 无光
        return _series(
            relative_humidity_2m=[(dawn, 97.0)], temperature_2m=[(dawn, 22.0)],
            dew_point_2m=[(dawn, 21.6)], wind_speed_10m=[(dawn, 1.5)],
            boundary_layer_height=[(dawn, 80.0)],
            cloud_cover_high=[(dawn, 90.0)])
    r = forecast_cloudsea(_client(shaded), LAT, LON, TZ, day)
    assert r["prob"] == 0 and "无光" in "".join(r["notes"])


def test_rainbow_no_potential_day():
    day = date(2026, 7, 11)
    r = forecast_rainbow(_client(lambda lat: _series()), LAT, LON, TZ, day)
    assert r["level"] == 0


def test_rainbow_l3_trigger_geometry():
    """全配触发:本地雨尾+反日扇区雨幕+光路开+仰角带内 → L3,几何字段齐。"""
    day = date(2026, 7, 11)
    now = datetime(2026, 7, 11, 19, 0, tzinfo=ZoneInfo(TZ))   # 日落约19:44
    def hourly(lat):
        if 39.70 <= lat <= 39.88:        # se25 反日扇区(≈39.81N):有雨幕
            return _series(precipitation=[("2026-07-11T19:00", 0.6),
                                          ("2026-07-11T20:00", 0.4)])
        if lat >= 40.05:                 # nw80 光路(≈40.22N):净
            return _series()
        # 本地:午后对流+雨尾
        return _series(
            precipitation=[("2026-07-11T16:00", 1.5), ("2026-07-11T18:00", 0.8),
                           ("2026-07-11T19:00", 0.2)],
            cloud_cover_mid=[(f"2026-07-11T{h:02d}:00", 60.0)
                             for h in range(14, 21)])
    r = forecast_rainbow(_client(hourly), LAT, LON, TZ, day, now=now)
    assert r["level"] == 3 and r["double_potential"] is True
    assert 100 <= r["antisolar_az"] <= 135      # 反日点在东南
    assert 30 <= r["bow_top"] <= 42             # 低太阳=高虹拱
    assert any("背对夕阳" in n for n in r["notes"])


def test_rainbow_blocked_light_path_stays_l2():
    """光路西北被中低云/雨封 → 不触发(停在就绪,并写明原因)。"""
    day = date(2026, 7, 11)
    now = datetime(2026, 7, 11, 19, 0, tzinfo=ZoneInfo(TZ))
    def hourly(lat):
        if 39.70 <= lat <= 39.88:
            return _series(precipitation=[("2026-07-11T19:00", 0.6)])
        if lat >= 40.05:                 # 光路:低云墙+雨
            return _series(cloud_cover_low=[("2026-07-11T19:00", 90.0)],
                           precipitation=[("2026-07-11T19:00", 1.0)])
        return _series(
            precipitation=[("2026-07-11T16:00", 1.5), ("2026-07-11T19:00", 0.2)],
            cloud_cover_mid=[(f"2026-07-11T{h:02d}:00", 60.0)
                             for h in range(14, 21)])
    r = forecast_rainbow(_client(hourly), LAT, LON, TZ, day, now=now)
    assert r["level"] == 2
    assert any("光路未开" in n for n in r["notes"])


def test_cloudsea_grid_gates():
    """区域图逐格三道门:满配格高分,大风格/遮光格归零。"""
    import numpy as np
    from skyfire.phenomena import cloudsea_grid
    n = 4
    f = {"t2": np.full((n, n), 22.0), "d2": np.full((n, n), 21.6),
         "rh2": np.full((n, n), 96.0), "wind": np.full((n, n), 1.5),
         "blh": np.full((n, n), 100.0), "mid": np.full((n, n), 5.0),
         "high": np.full((n, n), 10.0)}
    f["wind"][0][0] = 8.0     # 大风格:成雾门 0
    f["high"][1][1] = 90.0    # 遮光格:有光门 0
    g = cloudsea_grid(f)
    assert g[2][2] >= 80      # 满配景山档
    assert g[0][0] == 0 and g[1][1] == 0


def test_rainbow_grid_curtain_and_path():
    """区域图彩虹条件:反日雨幕+光路开→高分;光路堵→0;暴雨格→0。"""
    import numpy as np
    from skyfire.phenomena import rainbow_grid
    bbox = (114.8, 38.4, 118.6, 41.6)
    n = 16
    zeros = np.zeros((n, n))
    precip = np.zeros((n, n)); precip[8, 8] = 0.6   # 观测格自身雨尾/雨幕
    f = {"low": zeros.copy(), "mid": zeros.copy(), "high": zeros.copy(),
         "precip": precip}
    g = rainbow_grid(f, bbox, antisolar_az=115.0)
    assert g[8][8] >= 80      # 幕+尾+路开
    # 光路(西北)堵死同一格
    f2 = {"low": np.full((n, n), 90.0), "mid": zeros.copy(),
          "high": zeros.copy(), "precip": precip}
    g2 = rainbow_grid(f2, bbox, antisolar_az=115.0)
    assert g2[8][8] == 0


def test_bt_to_rain_equiv_tiers():
    """卫星冷顶→雨核当量:深对流核0.8/成片冷顶0.3/暖顶0(2km补25km盲区)。"""
    from skyfire.phenomena import bt_to_rain_equiv
    assert bt_to_rain_equiv(238.0, 250.0) == 0.8   # 深对流核
    assert bt_to_rain_equiv(248.0, 252.0) == 0.3   # 成片冷顶
    assert bt_to_rain_equiv(270.0, 275.0) == 0.0   # 暖顶不算雨核
