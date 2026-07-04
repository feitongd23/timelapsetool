"""可复用的预测计算(predict / notify / tick 共用,消除重复)。

compute_prediction:算分 + 落库 + 可选 LLM,返回结构化结果供上层 echo/格式化/推送。
HTTP 失败向上抛 httpx.HTTPError;全模式无数据抛 ValueError——由调用方决定如何呈现。
"""
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import httpx

from skyfire import store
from skyfire.config import City
from skyfire.consensus import consensus
from skyfire.geo import channel_points
from skyfire.llm import LlmResult, interpret
from skyfire.openmeteo import fetch_aod_at, fetch_channel_profile, fetch_point_forecast
from skyfire.rag import factor_vector, similar_cases_from
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score
from skyfire.suntimes import sun_window


@dataclass
class PredictionResult:
    city_name: str
    event: str
    day: date
    index: float
    confidence: str
    spread: float
    per_model: dict[str, float]
    blocked_points: int
    channel_factor: float
    aod: float | None
    channel_empty: bool
    peak: datetime
    azimuth: float
    llm: LlmResult | None


def compute_prediction(conn, client: httpx.Client, city: City, city_key: str,
                       event: str, day: date, run_llm: bool = True) -> PredictionResult:
    win = sun_window(city.lat, city.lon, city.timezone, day, event)
    iso_hour = win.peak.strftime("%Y-%m-%dT%H:00")
    geo_pts = channel_points(city.lat, city.lon, win.azimuth_deg)
    forecasts = fetch_point_forecast(client, city.lat, city.lon, city.timezone)
    aod = fetch_aod_at(client, city.lat, city.lon, city.timezone, iso_hour)
    channel = fetch_channel_profile(client, geo_pts, city.timezone, iso_hour)
    channel_empty = all(p.cloud_low is None and p.cloud_total is None for p in channel)

    per_model: dict[str, float] = {}
    details = {}
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None or h.cloud_high is None:
            continue
        r = fire_cloud_score(FireCloudInputs(
            cloud_high=h.cloud_high, cloud_mid=h.cloud_mid or 0,
            cloud_low=h.cloud_low or 0, precipitation=h.precipitation or 0,
            aod=aod, channel=channel,
        ))
        per_model[fc.model] = r.score
        details[fc.model] = r
    if not per_model:
        raise ValueError("所有模式数据缺失")

    cons = consensus(per_model)
    first = next(iter(details.values()))
    case_id = store.upsert_case(conn, str(day), city_key, event,
                                rule_score=cons.index, confidence=cons.confidence,
                                source="auto")
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None:
            continue
        store.add_snapshot(conn, case_id, fc.model, {
            "hour": iso_hour, "cloud_high": h.cloud_high, "cloud_mid": h.cloud_mid,
            "cloud_low": h.cloud_low, "cloud_cover": h.cloud_cover,
            "rh_2m": h.rh_2m, "precipitation": h.precipitation, "aod": aod,
            "channel": [{"km": p.dist_km, "low": p.cloud_low, "total": p.cloud_total}
                        for p in channel],
            "azimuth": round(win.azimuth_deg, 1),
        })

    llm_result = None
    if run_llm:
        gfs = next((fc for fc in forecasts if fc.model == "gfs_seamless"), forecasts[0])
        h0 = gfs.at(iso_hour)
        today = {"date": str(day), "event": event, "rule_score": cons.index,
                 "confidence": cons.confidence,
                 "payload": {"cloud_high": h0.cloud_high if h0 else None,
                             "cloud_mid": h0.cloud_mid if h0 else None,
                             "cloud_low": h0.cloud_low if h0 else None,
                             "rh_2m": h0.rh_2m if h0 else None, "aod": aod,
                             "channel": [{"km": p.dist_km, "low": p.cloud_low,
                                          "total": p.cloud_total} for p in channel],
                             "hour": iso_hour}}
        cases = store.cases_with_snapshot(conn, city_key, event, model="gfs_seamless")
        cases = [x for x in cases if x["case_id"] != case_id]
        similar = similar_cases_from(cases, factor_vector(today["payload"]), k=3)
        frames = [Path(f["path"]) for f in store.get_frames(conn, case_id)
                  if Path(f["path"]).exists()]
        llm_result = interpret(today, similar, frames)
        if llm_result is not None:
            store.set_llm_score(conn, case_id, llm_result.llm_score)

    return PredictionResult(
        city_name=city.name, event=event, day=day, index=cons.index,
        confidence=cons.confidence, spread=cons.spread, per_model=cons.per_model,
        blocked_points=first.blocked_points, channel_factor=first.channel_factor,
        aod=aod, channel_empty=channel_empty, peak=win.peak, azimuth=win.azimuth_deg,
        llm=llm_result)
