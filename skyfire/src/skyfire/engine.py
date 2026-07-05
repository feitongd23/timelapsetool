"""可复用的预测计算(predict / notify / tick 共用,消除重复)。

compute_prediction:算分 + 落库 + 可选 LLM,返回结构化结果供上层 echo/格式化/推送。
HTTP 失败向上抛 httpx.HTTPError;全模式无数据抛 ValueError——由调用方决定如何呈现。
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from skyfire import store
from skyfire.checkpoints import gate_exceeded
from skyfire.cloudiness import box_cloudiness
from skyfire.config import City
from skyfire.consensus import consensus
from skyfire.drift import estimate_shift, projected_box_cloudiness
from skyfire.geo import channel_points
from skyfire.himawari_hsd import (
    CROP_BBOX,
    download_segments,
    latest_slot,
    round_down_10min,
    segments_for,
)
from skyfire.llm import LlmResult, MODEL_DEEP, interpret, predict_pct
from skyfire.openmeteo import fetch_aod_at, fetch_channel_profile, fetch_point_forecast
from skyfire.percent import baseline_percent
from skyfire.rag import factor_vector, similar_cases_from
from skyfire.render import load_b13_region, render_annotated
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


def observe_burn_clouds(client, peak_utc, event: str, lat: float, lon: float,
                        frames_dir: Path,
                        ) -> tuple[float | None, float | None, str | None, list[Path]]:
    """实况层:当前实测云量、外推到燃烧时刻云量、趋势文本、判读图路径。

    尽力语义:卫星缺 → (None, None, None, [])。
    """
    try:
        now = datetime.now(timezone.utc)
        ts1 = latest_slot(client, now)
        if ts1 is None:
            return None, None, None, []
        segs = segments_for(CROP_BBOX[1], CROP_BBOX[3],
                            (CROP_BBOX[0] + CROP_BBOX[2]) / 2)
        cache = Path(frames_dir) / "hsd_cache"
        dats1 = download_segments(client, ts1, "B13", segs, cache)
        if not dats1:
            return None, None, None, []
        f1 = load_b13_region(dats1, CROP_BBOX, lat, lon)
        now_pct = box_cloudiness(f1.gray, f1.center_px, half=40)
        ts0 = round_down_10min(ts1 - timedelta(minutes=10))
        dats0 = download_segments(client, ts0, "B13", segs, cache)
        frames_ahead = max(0.0, (peak_utc - ts1).total_seconds() / 600)
        if dats0:
            f0 = load_b13_region(dats0, CROP_BBOX, lat, lon)
            shift = estimate_shift(f0.gray, f1.gray)
        else:
            shift = (0, 0)
        burn_pct = projected_box_cloudiness(f1.gray, f1.center_px, shift,
                                            round(frames_ahead), half=40)
        png = Path(frames_dir) / "live" / f"live_{ts1:%Y%m%d_%H%M}.png"
        # azimuth 只用于 live 图标注,粗值即可(西/东);精确方位角由 compute_prediction 另算
        render_annotated(dats1, "B13", CROP_BBOX, png, lat=lat, lon=lon,
                         azimuth_deg=270.0 if event == "sunset_glow" else 90.0)
        trend = f"现在{now_pct:.0f}% → 届时约{burn_pct:.0f}%"
        return round(now_pct, 1), round(burn_pct, 1), trend, [png]
    except (httpx.HTTPError, OSError):
        return None, None, None, []


def run_checkpoint(conn, client, city: City, city_key: str, event: str,
                   day, checkpoint: str, *, gate: bool = False,
                   frames_dir: Path = Path("data/frames"),
                   model: str | None = None) -> dict | None:
    """一个检查点:免费层 → (门控)→ LLM → 落 predictions,返回记录。

    gate=True 时先算免费层基线,与最新一版比较,|Δ概率|≤15pp → 返回 None
    (不落库不调 LLM)。LLM 失败/无 key → 基线落库 llm_status='pending'。
    """
    r = compute_prediction(conn, client, city, city_key, event, day,
                           run_llm=False)
    peak_utc = r.peak.astimezone(timezone.utc)
    sat_now, burn_pct, trend, live_frames = observe_burn_clouds(
        client, peak_utc, event, city.lat, city.lon, frames_dir)
    # C1 早间展望距燃烧还有数小时:短时外推冒充不了届时云况
    # (knowledge §3.2:远期信预报当底子,临近才信实测外推),
    # 基线只用预报驱动的规则分;C2/C3/gated 临近才引入卫星外推修正。
    cloud_args = (None, None) if checkpoint == "c1" else (sat_now, burn_pct)
    prob, qual = baseline_percent(r.index, r.confidence, *cloud_args)
    # 各模式单独换算(用户要求推送分模型;也喂给 LLM 看模式间分歧)
    per_model_pct = {m: baseline_percent(s, r.confidence, *cloud_args)
                     for m, s in r.per_model.items()}

    if gate:
        last = store.latest_prediction(conn, str(day), city_key, event)
        if not gate_exceeded(last["probability_pct"] if last else None, prob):
            return None

    from datetime import datetime as _dt
    hours_to_peak = round((peak_utc - _dt.now(timezone.utc)).total_seconds()
                          / 3600, 1)
    payload = {"date": str(day), "event": event, "checkpoint": checkpoint,
               "hours_to_peak": hours_to_peak,
               "rule_score": r.index, "confidence": r.confidence,
               "per_model": r.per_model, "per_model_pct": per_model_pct,
               "aod": r.aod,
               "sat_cloud_now": sat_now, "burn_cloud_projected": burn_pct,
               "trend": trend, "baseline_prob": prob, "baseline_quality": qual}
    cases = store.cases_with_snapshot(conn, city_key, event, model="gfs_seamless")
    similar = similar_cases_from(cases, factor_vector(payload), k=3)
    llm_r = predict_pct(payload, similar, live_frames,
                        model=model or _pick_model())
    if llm_r is not None:
        rec = dict(probability_pct=llm_r["probability_pct"],
                   quality_pct=llm_r["quality_pct"],
                   confidence=llm_r["confidence"], llm_status="done",
                   reasoning=llm_r["reasoning"], risks=llm_r["risks"])
    else:
        rec = dict(probability_pct=prob, quality_pct=qual,
                   confidence=r.confidence, llm_status="pending",
                   reasoning=None, risks=None)
    pred_id = store.add_prediction(
        conn, str(day), city_key, event, checkpoint,
        probability_pct=rec["probability_pct"], quality_pct=rec["quality_pct"],
        confidence=rec["confidence"], rule_score=r.index,
        sat_cloud_pct=sat_now, trend=trend, llm_status=rec["llm_status"],
        reasoning=rec["reasoning"], risks=rec["risks"])
    return {**rec, "id": pred_id, "date": str(day), "city": city_key,
            "event": event, "checkpoint": checkpoint, "rule_score": r.index,
            "sat_cloud_pct": sat_now, "trend": trend, "peak": r.peak,
            "per_model_pct": per_model_pct, "aod": r.aod,
            "city_name": city.name}


def _pick_model() -> str:
    # 用户 2026-07-05 拍板:日常检查点用 Sonnet 5(Haiku 推理深度不够,
    # 曾把干冷气团方向猜反;Sonnet 读图接近 Opus,月成本仍 <$6)。
    return MODEL_DEEP
