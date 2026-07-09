import json

import httpx

from skyfire.geo import GeoPoint
from skyfire.openmeteo import (
    MODELS,
    fetch_aod_at,
    fetch_aod_range,
    fetch_channel_profile,
    fetch_channel_profile_range,
    fetch_point_forecast,
)


def _multi_model_payload():
    times = ["2026-07-03T19:00", "2026-07-03T20:00"]
    hourly = {"time": times}
    for m in MODELS:
        hourly[f"cloud_cover_{m}"] = [60, 55]
        hourly[f"cloud_cover_low_{m}"] = [10, 12]
        hourly[f"cloud_cover_mid_{m}"] = [15, 14]
        hourly[f"cloud_cover_high_{m}"] = [48, 45]
        hourly[f"relative_humidity_2m_{m}"] = [70, 72]
        hourly[f"wind_speed_10m_{m}"] = [2.5, 2.8]
        hourly[f"temperature_2m_{m}"] = [30, 29]
        hourly[f"dew_point_2m_{m}"] = [22, 22]
        hourly[f"precipitation_{m}"] = [0, 0]
    return {"hourly": hourly}


def _client(payload):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_point_forecast_parses_all_models():
    client = _client(_multi_model_payload())
    forecasts = fetch_point_forecast(client, 39.9, 116.4, "Asia/Shanghai")
    assert [f.model for f in forecasts] == list(MODELS)
    h = forecasts[0].at("2026-07-03T19:00")
    assert h.cloud_high == 48 and h.cloud_low == 10
    assert forecasts[0].at("2099-01-01T00:00") is None


def test_fetch_point_forecast_tolerates_missing_variable():
    payload = _multi_model_payload()
    del payload["hourly"][f"cloud_cover_high_{MODELS[0]}"]  # EC 缺某变量
    client = _client(payload)
    forecasts = fetch_point_forecast(client, 39.9, 116.4, "Asia/Shanghai")
    assert forecasts[0].at("2026-07-03T19:00").cloud_high is None


def test_fetch_aod_at():
    payload = {"hourly": {"time": ["2026-07-03T19:00"], "aerosol_optical_depth": [0.35]}}
    client = _client(payload)
    assert fetch_aod_at(client, 39.9, 116.4, "Asia/Shanghai", "2026-07-03T19:00") == 0.35


def test_fetch_channel_profile():
    # 多地点请求返回 list;默认 GFS+EC 双模式,每点取最坏值(2026-07-09:
    # 通道曾 GFS 独家,报中云 5% 的那家垄断通道数据=同源谎言无法互检)
    t = ["2026-07-03T19:00"]
    payload = [
        {"hourly": {"time": t,
                    "cloud_cover_gfs_seamless": [80], "cloud_cover_ecmwf_ifs": [95],
                    "cloud_cover_low_gfs_seamless": [70], "cloud_cover_low_ecmwf_ifs": [10],
                    "cloud_cover_mid_gfs_seamless": [5], "cloud_cover_mid_ecmwf_ifs": [75]}},
        {"hourly": {"time": t,
                    "cloud_cover_gfs_seamless": [20], "cloud_cover_ecmwf_ifs": [15],
                    "cloud_cover_low_gfs_seamless": [5], "cloud_cover_low_ecmwf_ifs": [0],
                    "cloud_cover_mid_gfs_seamless": [0], "cloud_cover_mid_ecmwf_ifs": [10]}},
    ]
    client = _client(payload)
    pts = [GeoPoint(40.0, 115.0, 100), GeoPoint(40.1, 114.0, 200)]
    profile = fetch_channel_profile(client, pts, "Asia/Shanghai", "2026-07-03T19:00")
    assert len(profile) == 2
    assert profile[0].dist_km == 100 and profile[0].cloud_low == 70   # max(70,10)
    assert profile[0].cloud_mid == 75                                 # max(5,75)
    assert profile[0].cloud_total == 95
    assert profile[1].cloud_total == 20 and profile[1].cloud_mid == 10


def test_fetch_channel_profile_single_model_unsuffixed():
    payload = [{"hourly": {"time": ["2026-07-03T19:00"], "cloud_cover": [80],
                           "cloud_cover_low": [70], "cloud_cover_mid": [30]}}]
    client = _client(payload)
    profile = fetch_channel_profile(client, [GeoPoint(40.0, 115.0, 100)],
                                    "Asia/Shanghai", "2026-07-03T19:00",
                                    models=("gfs_seamless",))
    assert profile[0].cloud_low == 70 and profile[0].cloud_mid == 30


from skyfire.openmeteo import HISTORICAL_FORECAST_URL, fetch_point_forecast_range


def test_fetch_point_forecast_range_hits_historical_url_with_dates():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json=_multi_model_payload())

    client = httpx.Client(transport=httpx.MockTransport(handler))
    forecasts = fetch_point_forecast_range(client, 39.9, 116.4, "Asia/Shanghai",
                                           "2026-05-12", "2026-05-12")
    assert seen["host"] == httpx.URL(HISTORICAL_FORECAST_URL).host
    assert seen["params"]["start_date"] == "2026-05-12"
    assert seen["params"]["end_date"] == "2026-05-12"
    assert [f.model for f in forecasts] == list(MODELS)
    assert forecasts[0].at("2026-07-03T19:00").cloud_high == 48


def test_fetch_channel_profile_range_hits_historical_endpoint():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["host"] = request.url.host
        seen["params"] = dict(request.url.params)
        loc = {"hourly": {"time": ["2026-05-06T18:00", "2026-05-06T19:00"],
                          "cloud_cover": [70, 80], "cloud_cover_low": [10, 20]}}
        return httpx.Response(200, json=[loc, loc])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    pts = [GeoPoint(lat=40.0, lon=115.0, dist_km=100),
           GeoPoint(lat=40.1, lon=114.0, dist_km=200)]
    prof = fetch_channel_profile_range(client, pts, "Asia/Shanghai",
                                       "2026-05-06T19:00", "2026-05-06")
    assert seen["host"] == "historical-forecast-api.open-meteo.com"
    assert seen["params"]["start_date"] == "2026-05-06"
    assert [p.dist_km for p in prof] == [100, 200]
    assert prof[0].cloud_low == 20 and prof[0].cloud_total == 80


def test_fetch_aod_range_returns_value_or_none():
    def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params)["start_date"] == "2026-05-06"
        return httpx.Response(200, json={"hourly": {
            "time": ["2026-05-06T19:00"], "aerosol_optical_depth": [0.42]}})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_aod_range(client, 39.9, 116.4, "Asia/Shanghai",
                           "2026-05-06T19:00", "2026-05-06") == 0.42

    def handler_err(request):
        return httpx.Response(400)   # CAMS 存档边界外(<2022-07-29)
    client = httpx.Client(transport=httpx.MockTransport(handler_err))
    assert fetch_aod_range(client, 39.9, 116.4, "Asia/Shanghai",
                           "2020-09-01T18:00", "2020-09-01") is None


def test_apikey_switches_to_customer_hosts(monkeypatch):
    # 商用 key 存在 → customer-* 域名 + key 埋进 URL;无 key → 免费域名
    import importlib
    import skyfire.openmeteo as om
    monkeypatch.setenv("OPEN_METEO_APIKEY", "k123")
    importlib.reload(om)
    assert om.FORECAST_URL == "https://customer-api.open-meteo.com/v1/forecast?apikey=k123"
    assert "customer-air-quality-api" in om.AIR_QUALITY_URL
    monkeypatch.delenv("OPEN_METEO_APIKEY")
    importlib.reload(om)
    assert om.FORECAST_URL == "https://api.open-meteo.com/v1/forecast"
