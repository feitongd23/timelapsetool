"""云海与彩虹预测引擎(2026-07-11,用户拍板加入小程序)。

规则表口径强制过堂:
- 云海=规则表雾节三道门(knowledge 2022-08-19 满配归因):
  G1 成雾(T-Td/RH/风窗/湿源)× G2 雾顶够低(BLH 档位:景山CBD/香山)
  × G3 有光(上空中高云不遮日出)。三门相乘,任一门 0 则 0。
- 彩虹=四例实测配方(rainbow-forecast-recipe,n=4 初标定):
  L1 潜势日(午后对流雨+云量+气温+晚窗存在)→
  L3 触发(本地雨尾 × 反日扇区雨幕 × 光路开 × 太阳仰角 0-42°)。
数据:Open-Meteo 单点 hourly(GFS,含 BLH/能见度),配额当量个位数。
"""
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from skyfire.geo import destination
from skyfire.suntimes import sun_window

_VARS = ("precipitation,relative_humidity_2m,wind_speed_10m,temperature_2m,"
         "dew_point_2m,cloud_cover_low,cloud_cover_mid,cloud_cover_high,"
         "boundary_layer_height,visibility")


def _hourly(client: httpx.Client, lat: float, lon: float, tz: str,
            past_days: int = 1, forecast_days: int = 2) -> dict:
    from skyfire.openmeteo import FORECAST_URL
    r = client.get(FORECAST_URL, params={
        "latitude": lat, "longitude": lon, "timezone": tz,
        "hourly": _VARS, "models": "gfs_seamless",
        "wind_speed_unit": "ms",
        "past_days": past_days, "forecast_days": forecast_days})
    r.raise_for_status()
    return r.json()["hourly"]


def _at(h: dict, iso: str, var: str):
    try:
        return h[var][h["time"].index(iso)]
    except (KeyError, ValueError, IndexError):
        return None


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:00")


# ---------- 云海(三道门) ----------

def forecast_cloudsea(client: httpx.Client, lat: float, lon: float, tz: str,
                      day: date_type) -> dict:
    """day 清晨的城市低雾云海预报(观测点=山上/高楼向下看)。

    返回 {prob, tier, gates:{成雾,雾顶,有光}, sunrise, notes}。
    """
    win = sun_window(lat, lon, tz, day, "sunrise_glow")
    dawn = win.peak
    h = _hourly(client, lat, lon, tz)
    iso_dawn = _iso(dawn)

    t = _at(h, iso_dawn, "temperature_2m")
    td = _at(h, iso_dawn, "dew_point_2m")
    rh = _at(h, iso_dawn, "relative_humidity_2m")
    wind = _at(h, iso_dawn, "wind_speed_10m")
    blh = _at(h, iso_dawn, "boundary_layer_height")
    mid = _at(h, iso_dawn, "cloud_cover_mid")
    high = _at(h, iso_dawn, "cloud_cover_high")
    # 湿源:黎明前 24h 累计降水(前日透雨≥5mm 是 2022-08-19 满配环节之一)
    rain24 = 0.0
    for k in range(1, 25):
        v = _at(h, _iso(dawn - timedelta(hours=k)), "precipitation")
        rain24 += v or 0.0

    notes: list[str] = []
    gates: dict[str, float] = {}

    # G1 成雾:T-Td ≤1.5 且 RH≥93 且 风 0.5-4m/s;湿源加持
    if None in (t, td, rh, wind):
        return {"prob": 0, "tier": "数据缺失", "gates": {}, "notes": ["预报数据缺失"],
                "sunrise": dawn.strftime("%H:%M")}
    spread = t - td
    g1 = 0.0
    if spread <= 1.5 and rh >= 93 and 0.5 <= wind <= 4.0:
        g1 = 1.0
    elif spread <= 2.5 and rh >= 88 and wind <= 5.0:
        g1 = 0.5
        notes.append(f"成雾条件边缘(T-Td {spread:.1f}℃ RH{rh:.0f}% 风{wind:.1f}m/s)")
    else:
        notes.append(f"成雾门未过(T-Td {spread:.1f}℃ RH{rh:.0f}% 风{wind:.1f}m/s)")
    if g1 > 0 and rain24 >= 5.0:
        notes.append(f"前日透雨{rain24:.0f}mm,湿源充足")
        g1 = min(1.0, g1 + 0.25)

    # G2 雾顶够低:BLH 档位(knowledge:≤150m 景山/CBD 档,150-350 香山档)
    lcl = 125.0 * max(0.0, spread)   # LCL≈125×(T−Td) 交叉验证
    top = min(blh, lcl + 80) if blh is not None else lcl
    if top <= 150:
        g2, tier = 1.0, "景山CBD档"
    elif top <= 350:
        g2, tier = 0.8, "香山档"
    elif top <= 900:
        g2, tier = 0.3, "边缘档"
        notes.append(f"雾顶偏高(≈{top:.0f}m),只余高点俯瞰")
    else:
        g2, tier = 0.0, "无"
        notes.append(f"雾顶过高(≈{top:.0f}m),成层不成海")

    # G3 有光:日出时上空中高云 ≤30%(雾海要被照亮才值得拍)
    shade = max(mid or 0, high or 0)
    if shade <= 30:
        g3 = 1.0
    elif shade <= 60:
        g3 = 0.5
        notes.append(f"上空中高云{shade:.0f}%,光被滤弱")
    else:
        g3 = 0.0
        notes.append(f"上空中高云{shade:.0f}%,无光照海")

    prob = int(round(100 * g1 * g2 * g3))
    if prob == 0:
        tier = "无"
    return {"prob": prob, "tier": tier,
            "gates": {"成雾": round(g1, 2), "雾顶": round(g2, 2), "有光": round(g3, 2)},
            "notes": notes, "sunrise": dawn.strftime("%H:%M")}


# ---------- 彩虹(L1 潜势 / L3 触发) ----------

@dataclass
class RainbowStatus:
    level: int          # 0 无 / 1 潜势日 / 2 就绪 / 3 触发
    label: str
    window: str
    sun_elev: float | None
    antisolar_az: float | None
    bow_top: float | None
    double_potential: bool
    notes: list


def forecast_rainbow(client: httpx.Client, lat: float, lon: float, tz: str,
                     day: date_type, now: datetime | None = None) -> dict:
    """晚窗彩虹雷达(晨窗镜像待样本)。四例实测配方,阈值 n=4 初标定。"""
    from astral import Observer
    from astral.sun import azimuth, elevation

    tzinfo = ZoneInfo(tz)
    now = now or datetime.now(tzinfo)
    win = sun_window(lat, lon, tz, day, "sunset_glow")
    sunset = win.peak
    w_start = sunset - timedelta(hours=3, minutes=15)
    w_end = sunset - timedelta(minutes=5)
    window_s = f"{w_start:%H:%M}-{w_end:%H:%M}"
    notes: list[str] = []

    h = _hourly(client, lat, lon, tz)

    # L1 潜势:午后(14-20时)有对流性降水 且 午后云量>40 且 气温>8
    conv = any((_at(h, f"{day}T{hh:02d}:00", "precipitation") or 0) >= 0.3
               for hh in range(14, 21))
    cloudy = any(max(_at(h, f"{day}T{hh:02d}:00", "cloud_cover_low") or 0,
                     _at(h, f"{day}T{hh:02d}:00", "cloud_cover_mid") or 0,
                     _at(h, f"{day}T{hh:02d}:00", "cloud_cover_high") or 0) > 40
                 for hh in range(14, 21))
    warm = (_at(h, f"{day}T15:00", "temperature_2m") or 0) > 8
    if not (conv and cloudy and warm):
        return RainbowStatus(0, "无潜势", window_s, None, None, None, False,
                             ["今日无午后对流雨潜势"]).__dict__

    level, label = 1, "潜势日"
    sun_elev = antisolar = bow = None
    double = False

    in_window = w_start <= now <= w_end
    if in_window:
        obs = Observer(lat, lon)
        sun_elev = round(elevation(obs, now), 1)
        sun_az = azimuth(obs, now)
        antisolar = round((sun_az + 180) % 360, 0)
        bow = round(42 - sun_elev, 0)
        if 0 < sun_elev < 42:
            # 三点采样:本地雨尾 × 反日扇区(东南25km)雨幕 × 光路(西北80km)开
            se = destination(lat, lon, antisolar, 25)
            nw = destination(lat, lon, sun_az, 80)
            h_se = _hourly(client, se[0], se[1], tz, past_days=0, forecast_days=1)
            h_nw = _hourly(client, nw[0], nw[1], tz, past_days=0, forecast_days=1)
            iso_now = _iso(now)
            iso_next = _iso(now + timedelta(hours=1))
            local_now = _at(h, iso_now, "precipitation") or 0
            local_prev = _at(h, _iso(now - timedelta(hours=1)), "precipitation") or 0
            rain_tail = (0 < local_now <= 1.0) or (local_prev > 0 and local_now <= 0.3)
            curtain = max(_at(h_se, iso_now, "precipitation") or 0,
                          _at(h_se, iso_next, "precipitation") or 0)
            nw_low = max(_at(h_nw, iso_now, "cloud_cover_low") or 0,
                         _at(h_nw, iso_now, "cloud_cover_mid") or 0)
            nw_rain = _at(h_nw, iso_now, "precipitation") or 0
            path_open = nw_low <= 40 and nw_rain < 0.2
            has_curtain = curtain >= 0.1 or local_now > 0   # 痕量即可(四例实证)
            if rain_tail or has_curtain:
                level, label = 2, "就绪"
            if has_curtain and path_open and (rain_tail or curtain >= 0.1):
                level, label = 3, "触发"
                double = curtain >= 0.5
                notes.append(f"背对夕阳面向{antisolar:.0f}°,虹顶仰角约{bow:.0f}°")
                if double:
                    notes.append("反日扇区雨强足,留意双彩虹")
            else:
                if not path_open:
                    notes.append(f"光路未开(西北中低云{nw_low:.0f}%/雨{nw_rain:.1f}mm)")
                if not has_curtain:
                    notes.append("反日扇区暂无雨幕")
        else:
            notes.append("太阳仰角出虹几何区间")
    else:
        notes.append(f"晚窗 {window_s},届时自动评估")

    return RainbowStatus(level, label, window_s, sun_elev, antisolar, bow,
                         double, notes).__dict__


# ---------- 京津区域图(用户 2026-07-11:云海彩虹只服务北京,带上天津) ----------

def cloudsea_grid(f: dict) -> list:
    """逐格三道门连乘 → 云海概率网格(输入=fetch_gfs_jingjin 黎明时次场)。"""
    import numpy as np
    spread = f["t2"] - f["d2"]
    rh, wind, blh = f["rh2"], f.get("wind"), f["blh"]
    if wind is None:
        wind = np.full_like(rh, 2.0)
    g1 = np.where((spread <= 1.5) & (rh >= 93) & (wind >= 0.5) & (wind <= 4.0), 1.0,
                  np.where((spread <= 2.5) & (rh >= 88) & (wind <= 5.0), 0.5, 0.0))
    lcl = 125.0 * np.clip(spread, 0, None)
    top = np.minimum(blh, lcl + 80)
    g2 = np.where(top <= 150, 1.0,
                  np.where(top <= 350, 0.8, np.where(top <= 900, 0.3, 0.0)))
    shade = np.maximum(f["mid"], f["high"])
    g3 = np.where(shade <= 30, 1.0, np.where(shade <= 60, 0.5, 0.0))
    grid = (100.0 * g1 * g2 * g3)
    return [[float(v) for v in row] for row in grid]


def rainbow_grid(f: dict, bbox, antisolar_az: float) -> list:
    """逐格彩虹条件网格(晚窗时次):本地雨尾/邻近雨幕 × 反日扇区 × 光路开。"""
    import math

    import numpy as np

    from skyfire.heatgrid import _sample_grid

    precip = f.get("precip")
    low, mid = f["low"], f["mid"]
    rows, cols = low.shape
    lon0, lat0, lon1, lat1 = bbox
    pr_l = [[float(v) for v in r] for r in precip] if precip is not None else None
    low_l = [[float(v) for v in r] for r in low]
    mid_l = [[float(v) for v in r] for r in mid]
    sun_az = (antisolar_az + 180) % 360
    rad_a = math.radians(antisolar_az)
    rad_s = math.radians(sun_az)
    out = [[0.0] * cols for _ in range(rows)]
    if pr_l is None:
        return out
    for r in range(rows):
        lat = lat1 - (lat1 - lat0) * r / max(1, rows - 1)
        coslat = max(0.2, math.cos(math.radians(lat)))
        for c in range(cols):
            lon = lon0 + (lon1 - lon0) * c / max(1, cols - 1)
            # 反日扇区 25km 雨幕(含本格雨尾)
            alat = lat + 25 * math.cos(rad_a) / 111.0
            alon = lon + 25 * math.sin(rad_a) / (111.0 * coslat)
            curtain = max(pr_l[r][c],
                          _sample_grid(pr_l, bbox, alon, alat) or 0.0)
            # 光路 80km(太阳方向)开:中低云≤40 且基本无雨
            slat = lat + 80 * math.cos(rad_s) / 111.0
            slon = lon + 80 * math.sin(rad_s) / (111.0 * coslat)
            p_low = _sample_grid(low_l, bbox, slon, slat)
            p_mid = _sample_grid(mid_l, bbox, slon, slat)
            p_pr = _sample_grid(pr_l, bbox, slon, slat)
            blocked = (max(p_low or 0, p_mid or 0) > 40
                       or (p_pr or 0) >= 0.2)
            if curtain >= 0.1 and not blocked and pr_l[r][c] <= 1.5:
                score = 70.0 + (15.0 if curtain >= 0.5 else 0.0) \
                    + (10.0 if 0.02 < pr_l[r][c] <= 1.0 else 0.0)
                out[r][c] = min(95.0, score)
    return out


def refresh_phenomena_maps(client: httpx.Client, city, out_dir,
                           kinds: tuple = ("sea", "rainbow")) -> dict:
    """京津云海/彩虹区域图落盘。云海=明晨;彩虹=当前晚窗时次(窗外跳过)。"""
    from datetime import date as date_type
    from pathlib import Path

    from astral import Observer
    from astral.sun import azimuth, elevation

    from skyfire.gribmaps import (JINGJIN_BBOX, fetch_gfs_jingjin,
                                  latest_gfs_run)
    from skyfire.heatmap_map import render_map_png

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    run = latest_gfs_run(client)
    if run is None:
        return written
    tzinfo = ZoneInfo(city.timezone)
    now = datetime.now(tzinfo)

    if "sea" in kinds:
        sea_day = now.date() + timedelta(days=1)
        dawn = sun_window(city.lat, city.lon, city.timezone, sea_day,
                          "sunrise_glow").peak
        fh = round((dawn.astimezone(ZoneInfo("UTC")) - run).total_seconds() / 3600)
        if 0 < fh <= 120:
            f = fetch_gfs_jingjin(client, run, fh)
            if f is not None:
                grid = cloudsea_grid(f)
                png = render_map_png(grid, "sea", JINGJIN_BBOX,
                                     marker=(city.name, city.lat, city.lon),
                                     title=f"明晨云海 · 京津 · GFS {run:%d日%H}z"
                                           f" · {sea_day:%m-%d} 日出")
                p = out_dir / f"beijing_{sea_day}_cloudsea.png"
                p.write_bytes(png)
                written["sea"] = str(p)

    if "rainbow" in kinds:
        win = sun_window(city.lat, city.lon, city.timezone, now.date(),
                         "sunset_glow")
        w_start = win.peak - timedelta(hours=3, minutes=15)
        if w_start <= now <= win.peak:
            obs = Observer(city.lat, city.lon)
            if 0 < elevation(obs, now) < 42:
                anti = (azimuth(obs, now) + 180) % 360
                fh = round((now.astimezone(ZoneInfo("UTC")) - run
                            ).total_seconds() / 3600)
                if 0 < fh <= 120:
                    f = fetch_gfs_jingjin(client, run, fh)
                    if f is not None:
                        # 实时卫星雨核(2km)补模式(25km)的对流盲区:
                        # 莉景"卫星云图+光路"思路,窗口期实况优先
                        import numpy as _np
                        sat = satellite_rain_grid(client, JINGJIN_BBOX,
                                                  *f["low"].shape)
                        sat_tag = ""
                        if sat is not None:
                            base_pr = f.get("precip")
                            f["precip"] = (_np.maximum(base_pr, sat)
                                           if base_pr is not None else sat)
                            sat_tag = " · 结合实时卫星"
                        grid = rainbow_grid(f, JINGJIN_BBOX, anti)
                        png = render_map_png(
                            grid, "rainbow", JINGJIN_BBOX,
                            marker=(city.name, city.lat, city.lon),
                            title=f"彩虹条件 · 京津 · {now:%H:%M}"
                                  f" · 背对夕阳约{anti:.0f}°{sat_tag}")
                        p = out_dir / f"beijing_{now.date()}_rainbow.png"
                        p.write_bytes(png)
                        written["rainbow"] = str(p)
    return written


def bt_to_rain_equiv(min_bt: float, mean_bt: float) -> float:
    """B13 冷顶 → 雨核当量(mm/h 量级,喂给 rainbow_grid 的雨幕判据)。

    对流单体活在雷达/卫星尺度(2km),GFS 0.25° 会把它平均掉——
    莉景"卫星云图预测+光路"的思路(用户 2026-07-11 认可地图表达)。
    阈值:min_bt<242K=深对流核(强雨幕,给0.8);mean_bt<255K=成片冷顶
    (中等,给0.3);否则 0。粗代理,n 小待回测。
    """
    if min_bt < 242.0:
        return 0.8
    if mean_bt < 255.0:
        return 0.3
    return 0.0


def satellite_rain_grid(client: httpx.Client, bbox, rows: int, cols: int,
                        frames_dir="data/frames"):
    """最新 B13 帧 → 京津逐格雨核当量网格(2km 卫星补 25km 模式的对流盲区)。

    尽力语义:卫星缺 → None(调用方退回纯模式场)。
    """
    import numpy as np

    from skyfire.cloudiness import box_stats
    from skyfire.himawari_hsd import (CROP_BBOX, download_segments,
                                      latest_slot, segments_for)
    from skyfire.render import load_b13_region
    try:
        from pathlib import Path
        now = datetime.now(ZoneInfo("UTC"))
        ts = latest_slot(client, now)
        if ts is None:
            return None
        segs = segments_for(CROP_BBOX[1], CROP_BBOX[3],
                            (CROP_BBOX[0] + CROP_BBOX[2]) / 2)
        dats = download_segments(client, ts, "B13", segs,
                                 Path(frames_dir) / "hsd_cache")
        if not dats:
            return None
        f = load_b13_region(dats, CROP_BBOX, 39.9042, 116.4074)
        if f.area is None:
            return None
        lon0, lat0, lon1, lat1 = bbox
        out = np.zeros((rows, cols))
        for r in range(rows):
            lat = lat1 - (lat1 - lat0) * r / max(1, rows - 1)
            for c in range(cols):
                lon = lon0 + (lon1 - lon0) * c / max(1, cols - 1)
                try:
                    px, py = f.area.get_xy_from_lonlat(lon, lat)
                except Exception:
                    continue
                s = box_stats(f.gray, (int(px), int(py)), half=7)
                if s is not None:
                    out[r, c] = bt_to_rain_equiv(
                        _min_bt_of(f.gray, int(px), int(py)), s["mean_bt"])
        return out
    except Exception:
        return None


def _min_bt_of(gray, px: int, py: int, half: int = 7) -> float:
    """窗内最冷亮温(gray 最大值=最冷)。"""
    from skyfire.cloudiness import gray_to_bt
    x0, x1 = max(px - half, 0), px + half
    y0, y1 = max(py - half, 0), py + half
    box = gray[y0:y1, x0:x1]
    if box.size == 0:
        return 300.0
    return gray_to_bt(float(box.max()))
