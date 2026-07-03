"""Open-Meteo 数据采集:多模式点预报、AOD、通道剖面批量查询。"""
import httpx

from skyfire.geo import GeoPoint
from skyfire.models import ChannelPoint, HourlyPoint, ModelForecast

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

MODELS = ("ecmwf_ifs025", "gfs_seamless", "icon_seamless", "cma_grapes_global")

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
    hourly = resp.json()["hourly"]
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
    model: str = "gfs_seamless",
) -> list[ChannelPoint]:
    """通道剖面:多地点一次请求(逗号分隔),单模式(MVP 用 GFS)。"""
    resp = client.get(FORECAST_URL, params={
        "latitude": ",".join(str(round(p.lat, 3)) for p in points),
        "longitude": ",".join(str(round(p.lon, 3)) for p in points),
        "timezone": tz, "hourly": "cloud_cover,cloud_cover_low",
        "models": model, "forecast_days": 3,
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
