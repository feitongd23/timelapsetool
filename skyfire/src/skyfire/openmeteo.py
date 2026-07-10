"""Open-Meteo 数据采集:多模式点预报、AOD、通道剖面批量查询。"""
import os

import httpx

from skyfire.geo import GeoPoint
from skyfire.models import ChannelPoint, HourlyPoint, ModelForecast

# 商用 key(环境变量 OPEN_METEO_APIKEY):切 customer-* 域名并携带 key,
# 配额100万当量/天;免费层约1万/天(全国图一刷≈4400)撑不住线上运行。
# httpx 会把 params 合并进 URL 自带 query,故 key 直接埋在常量 URL 里即可。
_KEY = os.environ.get("OPEN_METEO_APIKEY", "")


def _u(host: str, path: str) -> str:
    if _KEY:
        return f"https://customer-{host}.open-meteo.com{path}?apikey={_KEY}"
    return f"https://{host}.open-meteo.com{path}"


FORECAST_URL = _u("api", "/v1/forecast")
HISTORICAL_FORECAST_URL = _u("historical-forecast-api", "/v1/forecast")
AIR_QUALITY_URL = _u("air-quality-api", "/v1/air-quality")

# EC 用 IFS HRES 9km(ecmwf_ifs,2025-10 起 CC-BY 开放,与 Windy 展示同源同分辨率;
# 分层云量齐全且比 0.25° 版早约 45 分钟入库)。历史快照/回测仍存 ecmwf_ifs025 名。
MODELS = ("ecmwf_ifs", "gfs_seamless", "icon_seamless", "cma_grapes_global")

HOURLY_VARS = (
    "cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    "relative_humidity_2m", "wind_speed_10m", "temperature_2m", "dew_point_2m",
    "precipitation",
)

_FIELD_BY_VAR = {
    "cloud_cover": "cloud_cover", "cloud_cover_low": "cloud_low",
    "cloud_cover_mid": "cloud_mid", "cloud_cover_high": "cloud_high",
    "relative_humidity_2m": "rh_2m", "wind_speed_10m": "wind_speed",
    "temperature_2m": "temperature", "dew_point_2m": "dew_point",
    "precipitation": "precipitation",
}


def _series(hourly: dict, var: str, model_suffix: str, n: int) -> list:
    key = f"{var}{model_suffix}"
    values = hourly.get(key)
    if values is None:
        return [None] * n
    return values


def _parse_models(data: dict, models: tuple[str, ...]) -> list[ModelForecast]:
    hourly = data["hourly"]
    times = hourly["time"]
    result = []
    for m in models:
        suffix = f"_{m}" if len(models) > 1 else ""
        columns = {
            field: _series(hourly, var, suffix, len(times))
            for var, field in _FIELD_BY_VAR.items()
        }
        points = [
            HourlyPoint(time=t, **{f: columns[f][i] for f in columns})
            for i, t in enumerate(times)
        ]
        result.append(ModelForecast(model=m, hourly=points))
    return result


def fetch_point_forecast(
    client: httpx.Client, lat: float, lon: float, tz: str,
    models: tuple[str, ...] = MODELS, forecast_days: int = 3,
) -> list[ModelForecast]:
    resp = client.get(FORECAST_URL, params={
        "latitude": lat, "longitude": lon, "timezone": tz,
        "hourly": ",".join(HOURLY_VARS), "models": ",".join(models),
        "wind_speed_unit": "ms", "forecast_days": forecast_days,
    })
    resp.raise_for_status()
    return _parse_models(resp.json(), models)


def fetch_point_forecast_range(
    client: httpx.Client, lat: float, lon: float, tz: str,
    start_date: str, end_date: str, models: tuple[str, ...] = MODELS,
) -> list[ModelForecast]:
    """历史预报存档(冷启动回填用,spec 6.1):同一解析,不同端点+日期窗。"""
    resp = client.get(HISTORICAL_FORECAST_URL, params={
        "latitude": lat, "longitude": lon, "timezone": tz,
        "hourly": ",".join(HOURLY_VARS), "models": ",".join(models),
        "wind_speed_unit": "ms", "start_date": start_date, "end_date": end_date,
    })
    resp.raise_for_status()
    return _parse_models(resp.json(), models)


def fetch_aod_at(client: httpx.Client, lat: float, lon: float, tz: str, iso_hour: str) -> float | None:
    resp = client.get(AIR_QUALITY_URL, params={
        "latitude": lat, "longitude": lon, "timezone": tz,
        "hourly": "aerosol_optical_depth",
    })
    resp.raise_for_status()
    hourly = resp.json()["hourly"]
    for t, v in zip(hourly["time"], hourly["aerosol_optical_depth"]):
        if t == iso_hour:
            return v
    return None


def fetch_channel_profile(
    client: httpx.Client, points: list[GeoPoint], tz: str, iso_hour: str,
    models: tuple[str, ...] = ("gfs_seamless", "ecmwf_ifs"),
) -> list[ChannelPoint]:
    """通道剖面:多地点一次请求(逗号分隔),多模式最坏值合并。

    2026-07-09 复盘:通道曾 GFS 独家,而 GFS 正是把中云报成 5% 的那家——
    同源谎言无法互检。改为 GFS+EC 双模式,每点取各层最大值(保守),并加采
    中云(中云墙挡平射光)。仍是单请求,配额当量不变量级。
    """
    resp = client.get(FORECAST_URL, params={
        "latitude": ",".join(str(round(p.lat, 3)) for p in points),
        "longitude": ",".join(str(round(p.lon, 3)) for p in points),
        "timezone": tz,
        "hourly": "cloud_cover,cloud_cover_low,cloud_cover_mid,precipitation",
        "models": ",".join(models), "forecast_days": 3,
    })
    resp.raise_for_status()
    data = resp.json()
    locations = data if isinstance(data, list) else [data]
    suffixes = [f"_{m}" for m in models] if len(models) > 1 else [""]

    def _worst(hourly: dict, var: str, idx: int) -> float | None:
        vals = [hourly.get(f"{var}{s}", [None] * (idx + 1))[idx]
                for s in suffixes]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None

    profile = []
    for geo, loc in zip(points, locations):
        hourly = loc["hourly"]
        low = total = mid = pr = None
        for i, t in enumerate(hourly["time"]):
            if t == iso_hour:
                total = _worst(hourly, "cloud_cover", i)
                low = _worst(hourly, "cloud_cover_low", i)
                mid = _worst(hourly, "cloud_cover_mid", i)
                pr = _worst(hourly, "precipitation", i)
                break
        profile.append(ChannelPoint(dist_km=geo.dist_km, cloud_low=low,
                                    cloud_total=total, cloud_mid=mid,
                                    precip=pr))
    return profile


def fetch_channel_profile_range(
    client: httpx.Client, points: list[GeoPoint], tz: str, iso_hour: str,
    date: str, model: str = "gfs_seamless",
) -> list[ChannelPoint]:
    """历史通道剖面(冷启动回填用):同 fetch_channel_profile,走历史存档端点。

    救活 G_channel 硬门槛(knowledge §2-A):回填案例此前 channel=[] 恒中性。
    """
    resp = client.get(HISTORICAL_FORECAST_URL, params={
        "latitude": ",".join(str(round(p.lat, 3)) for p in points),
        "longitude": ",".join(str(round(p.lon, 3)) for p in points),
        "timezone": tz, "hourly": "cloud_cover,cloud_cover_low",
        "models": model, "start_date": date, "end_date": date,
    })
    resp.raise_for_status()
    data = resp.json()
    locations = data if isinstance(data, list) else [data]
    profile = []
    for geo, loc in zip(points, locations):
        hourly = loc["hourly"]
        low = total = None
        for i, t in enumerate(hourly["time"]):
            if t == iso_hour:
                total = hourly["cloud_cover"][i]
                low = hourly["cloud_cover_low"][i]
                break
        profile.append(ChannelPoint(dist_km=geo.dist_km, cloud_low=low, cloud_total=total))
    return profile


def fetch_aod_range(client: httpx.Client, lat: float, lon: float, tz: str,
                    iso_hour: str, date: str) -> float | None:
    """历史 AOD(尽力):CAMS 存档约 2022-07-29 起,边界外/失败返回 None。"""
    try:
        resp = client.get(AIR_QUALITY_URL, params={
            "latitude": lat, "longitude": lon, "timezone": tz,
            "hourly": "aerosol_optical_depth",
            "start_date": date, "end_date": date,
        })
        resp.raise_for_status()
        hourly = resp.json()["hourly"]
        for t, v in zip(hourly["time"], hourly["aerosol_optical_depth"]):
            if t == iso_hour:
                return v
    except (httpx.HTTPError, KeyError, ValueError):
        return None
    return None
