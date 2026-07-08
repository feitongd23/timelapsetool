"""辅助数据源(小程序 v2 界面用):逐小时天气、AQI、街区级逆地理。

全部尽力语义:主源失败走兜底或返回占位,不抛给端点 500。
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from skyfire.openmeteo import AIR_QUALITY_URL, FORECAST_URL

# 美使馆空气数据公开通道(AirNow DOS);不通时兜底 Open-Meteo PM2.5 换算
EMBASSY_FEED = "https://dosairnowdata.org/dos/AllPostsNowCastJSON.json"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"

_WEATHER_ZH = {0: "晴", 1: "晴", 2: "多云", 3: "阴", 45: "雾", 48: "雾",
               51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨", 61: "小雨", 63: "中雨",
               65: "大雨", 66: "冻雨", 67: "冻雨", 71: "小雪", 73: "中雪",
               75: "大雪", 77: "米雪", 80: "阵雨", 81: "阵雨", 82: "强阵雨",
               85: "阵雪", 86: "阵雪", 95: "雷雨", 96: "雷雨", 99: "雷雨"}


def fetch_hourly(client: httpx.Client, lat: float, lon: float, tz: str,
                 hours: int = 8) -> list[dict]:
    """从当前小时起的基础逐小时天气(温度/天气/云量/降水)。"""
    r = client.get(FORECAST_URL, params={
        "latitude": lat, "longitude": lon, "timezone": tz,
        "hourly": "temperature_2m,weather_code,cloud_cover,precipitation",
        "forecast_days": 2})
    r.raise_for_status()
    h = r.json()["hourly"]
    now_iso = datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%dT%H:00")
    idx = next((i for i, t in enumerate(h["time"]) if t >= now_iso), 0)
    out = []
    for i in range(idx, min(idx + hours, len(h["time"]))):
        code = h["weather_code"][i]
        precip = h["precipitation"][i] or 0
        out.append({"hour": int(h["time"][i][11:13]),
                    "temp": round(h["temperature_2m"][i]),
                    "text": "雨" if precip >= 0.1 else _WEATHER_ZH.get(code, "多云"),
                    "cloud": h["cloud_cover"][i],
                    "precip": precip})
    return out


def _pm25_to_aqi(c: float) -> int:
    """US EPA PM2.5 → AQI 分段线性。"""
    bps = [(0.0, 12.0, 0, 50), (12.1, 35.4, 51, 100), (35.5, 55.4, 101, 150),
           (55.5, 150.4, 151, 200), (150.5, 250.4, 201, 300),
           (250.5, 500.4, 301, 500)]
    for lo, hi, alo, ahi in bps:
        if lo <= c <= hi:
            return round((ahi - alo) / (hi - lo) * (c - lo) + alo)
    return 500


def _aqi_level(a: int) -> str:
    for th, name in [(50, "优"), (100, "良"), (150, "轻度污染"),
                     (200, "中度污染"), (300, "重度污染")]:
        if a <= th:
            return name
    return "严重污染"


def fetch_aqi(client: httpx.Client, lat: float, lon: float, tz: str) -> dict:
    """AQI:美使馆 NowCast 优先,不通则 Open-Meteo PM2.5 按 EPA 公式换算。"""
    try:
        r = client.get(EMBASSY_FEED)
        r.raise_for_status()
        for p in r.json():
            name = str(p.get("stationName") or p.get("city") or "")
            if "Beijing" in name or "北京" in name:
                aqi = int(p["aqi"])
                ts = str(p.get("localTimeStamp") or "")
                return {"aqi": aqi, "level": _aqi_level(aqi),
                        "pm25": p.get("conc"), "source": "北京美使馆",
                        "time": ts[11:16] if len(ts) >= 16 else ts}
    except Exception:
        pass
    r = client.get(AIR_QUALITY_URL, params={
        "latitude": lat, "longitude": lon, "timezone": tz, "hourly": "pm2_5"})
    r.raise_for_status()
    h = r.json()["hourly"]
    now_iso = datetime.now(ZoneInfo(tz)).strftime("%Y-%m-%dT%H:00")
    best = None
    for t, v in zip(h["time"], h["pm2_5"]):
        if v is not None and t <= now_iso:
            best = (t, v)
    if best is None:
        best = next(((t, v) for t, v in zip(h["time"], h["pm2_5"])
                     if v is not None), None)
    if best is None:
        return {"aqi": None, "level": "暂缺", "pm25": None,
                "source": "CAMS", "time": ""}
    t, pm = best
    aqi = _pm25_to_aqi(pm)
    return {"aqi": aqi, "level": _aqi_level(aqi), "pm25": round(pm),
            "source": "CAMS", "time": t[11:16]}


def reverse_name(client: httpx.Client, lat: float, lon: float) -> dict:
    """街区级地名(OSM Nominatim,尽力)。返回 {"name","district"}。"""
    try:
        r = client.get(NOMINATIM_URL, params={
            "lat": lat, "lon": lon, "format": "jsonv2",
            "accept-language": "zh", "zoom": 14},
            headers={"User-Agent": "skyfire/1.0 (personal weather miniapp)"})
        r.raise_for_status()
        a = r.json().get("address", {})
        name = (a.get("neighbourhood") or a.get("suburb") or a.get("quarter")
                or a.get("town") or a.get("village") or "")
        district = (a.get("district") or a.get("city_district")
                    or a.get("county") or "")
        return {"name": name or district or "你的位置", "district": district}
    except Exception:
        return {"name": "你的位置", "district": ""}
