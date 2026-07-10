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
