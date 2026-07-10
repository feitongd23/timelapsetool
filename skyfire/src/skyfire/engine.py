"""可复用的预测计算(predict / notify / tick 共用,消除重复)。

compute_prediction:算分 + 落库 + 可选 LLM,返回结构化结果供上层 echo/格式化/推送。
HTTP 失败向上抛 httpx.HTTPError;全模式无数据抛 ValueError——由调用方决定如何呈现。
"""
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from skyfire import store
from skyfire.checkpoints import gate_exceeded
from skyfire.cloudiness import box_cloudiness, box_stats
from skyfire.config import City
from skyfire.consensus import consensus, detect_split
from skyfire.drift import (RESPONSE_FLOOR, estimate_shift_quality,
                           projected_box_cloudiness)
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
from skyfire.skill import weights_from_skill
from skyfire.render import load_b13_region, render_annotated
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score
from skyfire.suntimes import nearest_iso_hour, sun_window


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
    # 各模式燃烧时刻原始预报(喂 LLM 看分歧;值可为 None)
    per_model_raw: dict[str, dict] = field(default_factory=dict)


def compute_prediction(conn, client: httpx.Client, city: City, city_key: str,
                       event: str, day: date, run_llm: bool = True) -> PredictionResult:
    win = sun_window(city.lat, city.lon, city.timezone, day, event)
    iso_hour = nearest_iso_hour(win.peak)
    geo_pts = channel_points(city.lat, city.lon, win.azimuth_deg)
    forecasts = fetch_point_forecast(client, city.lat, city.lon, city.timezone)
    aod = fetch_aod_at(client, city.lat, city.lon, city.timezone, iso_hour)
    channel = fetch_channel_profile(client, geo_pts, city.timezone, iso_hour)
    channel_empty = all(p.cloud_low is None and p.cloud_total is None for p in channel)

    per_model: dict[str, float] = {}
    per_model_raw: dict[str, dict] = {}
    details = {}
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None:
            continue
        per_model_raw[fc.model] = {
            "cloud_high": h.cloud_high, "cloud_mid": h.cloud_mid,
            "cloud_low": h.cloud_low, "precipitation": h.precipitation}
        if h.cloud_high is None:
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

    # 模式置信账本(skyfire modelskill 维护):样本攒够 → 按历史准确度加权
    skill_rows = store.get_model_skill(conn)
    weights = (weights_from_skill(skill_rows, list(per_model))
               if skill_rows else None)
    cons = consensus(per_model, weights=weights)
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
        llm=llm_result, per_model_raw=per_model_raw)


def score_location(client: httpx.Client, lat: float, lon: float, tz: str,
                   event: str, day: date, *, skill_rows=None) -> dict:
    """任意坐标的火烧云物理分(不写库,供按用户定位给位置专属预测)。

    画布(云高分层)× 透光通道(按该点日照方向采样)× 本地低云 × 气溶胶 × 降水
    → 免费层概率/质量。位置影响主要经"该点西/东侧透光通道"体现(用户 2026-07-08)。
    """
    win = sun_window(lat, lon, tz, day, event)
    iso = nearest_iso_hour(win.peak)
    channel = fetch_channel_profile(
        client, channel_points(lat, lon, win.azimuth_deg), tz, iso)
    aod = fetch_aod_at(client, lat, lon, tz, iso)
    per_model, totals = {}, []
    for fc in fetch_point_forecast(client, lat, lon, tz):
        h = fc.at(iso)
        if h is None or h.cloud_high is None:
            continue
        per_model[fc.model] = fire_cloud_score(FireCloudInputs(
            cloud_high=h.cloud_high, cloud_mid=h.cloud_mid or 0,
            cloud_low=h.cloud_low or 0, precipitation=h.precipitation or 0,
            aod=aod, channel=channel)).score
        totals.append(min(100.0, (h.cloud_high or 0) + (h.cloud_mid or 0)
                          + (h.cloud_low or 0)))
    if not per_model:
        raise ValueError("所有模式数据缺失")
    weights = weights_from_skill(skill_rows, list(per_model)) if skill_rows else None
    cons = consensus(per_model, weights=weights)
    total = sum(totals) / len(totals) if totals else None
    prob, qual = baseline_percent(cons.index, cons.confidence, None, total)
    return {"probability_pct": prob, "quality_pct": qual,
            "rule_score": round(cons.index, 1), "confidence": cons.confidence}


def observe_burn_clouds(client, peak_utc, event: str, lat: float, lon: float,
                        frames_dir: Path, azimuth_deg: float | None = None,
                        ) -> tuple[float | None, float | None, str | None,
                                   list[Path], dict | None]:
    """实况层:当前实测云量、外推到燃烧时刻云量、趋势文本、判读图、实况元信息。

    2026-07-09 0分复盘落下的三道强制检查(教训必须活在代码里):
    ①满盖检测——窗内最暖亮温低于当季晴地表下限=无一晴像元=满盖,线性读数
      按 ≥92 处理(红外暖顶陷阱,2026-06-26 初见、07-09 定量实锤:满盖中云
      被读成 34% 反拿甜区奖励);②判读图方位角用真值,不再硬编码 270/90
      (07-09 线偏 30.4° 把 LLM 视线引向云洞而非光路乌云墙);③光路上游
      100-300km 连续满盖时,外推结论标"云系压境",禁按"届时不变"呈现。
    尽力语义:卫星缺 → (None, None, None, [], None)。
    """
    try:
        now = datetime.now(timezone.utc)
        ts1 = latest_slot(client, now)
        if ts1 is None:
            return None, None, None, [], None
        segs = segments_for(CROP_BBOX[1], CROP_BBOX[3],
                            (CROP_BBOX[0] + CROP_BBOX[2]) / 2)
        cache = Path(frames_dir) / "hsd_cache"
        dats1 = download_segments(client, ts1, "B13", segs, cache)
        if not dats1:
            return None, None, None, [], None
        f1 = load_b13_region(dats1, CROP_BBOX, lat, lon)
        month = peak_utc.astimezone(timezone.utc).month
        stats = box_stats(f1.gray, f1.center_px, half=40, month=month)
        if stats is None:
            return None, None, None, [], None
        now_pct = stats["pct"]
        ts0 = round_down_10min(ts1 - timedelta(minutes=10))
        dats0 = download_segments(client, ts0, "B13", segs, cache)
        frames_ahead = max(0.0, (peak_utc - ts1).total_seconds() / 600)
        if dats0:
            f0 = load_b13_region(dats0, CROP_BBOX, lat, lon)
            dy, dx, resp = estimate_shift_quality(f0.gray, f1.gray)
            shift = (dy, dx)
        else:
            shift, resp = (0.0, 0.0), None
        # 峰质量门控(规则 nowcast-phasecorr-response-gate):碎峰=多层云
        # 各向异动/原地生消/纹理弱的指纹,矢量不可信 → 外推降级
        extrap_ok = resp is None or resp >= RESPONSE_FLOOR
        burn_pct = projected_box_cloudiness(f1.gray, f1.center_px, shift,
                                            round(frames_ahead), half=40)
        az = azimuth_deg if azimuth_deg is not None else (
            270.0 if event == "sunset_glow" else 90.0)
        # 光路上游平流检查:100-300km 三点窗满盖 → 云系正压向光路
        upstream_overcast = _upstream_overcast(f1, az, month)
        png = Path(frames_dir) / "live" / f"live_{ts1:%Y%m%d_%H%M}.png"
        render_annotated(dats1, "B13", CROP_BBOX, png, lat=lat, lon=lon,
                         azimuth_deg=az)
        frames = [png]
        # 白昼加可见光帧交叉验证厚度(规则 sat-visible-check:红外棕色区在
        # 可见光下大片亮白=厚中低云,一帧戳穿暖顶陷阱;2026-07-09 复盘——
        # 可见光在码库里现成却从没接进 live 链)。尽力语义,失败只丢这一帧。
        vis_attached = False
        try:
            from astral import Observer
            from astral.sun import elevation
            if elevation(Observer(lat, lon), ts1) > 10:
                dats_vis = download_segments(client, ts1, "B03", segs, cache)
                if dats_vis:
                    vis_png = (Path(frames_dir) / "live"
                               / f"live_{ts1:%Y%m%d_%H%M}_vis.png")
                    render_annotated(dats_vis, "B03", CROP_BBOX, vis_png,
                                     lat=lat, lon=lon, azimuth_deg=az)
                    frames.append(vis_png)
                    vis_attached = True
        except Exception:
            pass
        overcast = stats["overcast"]
        if stats["lid"]:
            # 暖顶盖子才强制 92;冷卷云幕满盖是画布,线性读数(50-70%)本身合理
            now_pct = max(now_pct, 92.0)
            burn_pct = max(burn_pct, 92.0)
            trend = (f"红外读数{stats['pct']:.0f}%,但窗内无晴像元且为暖顶"
                     f"(最暖{stats['max_bt']:.0f}K 均温{stats['mean_bt']:.0f}K)"
                     f"=中低云盖子,按{now_pct:.0f}%满盖处理")
        elif overcast:
            trend = (f"满盖冷云幕(最暖{stats['max_bt']:.0f}K):高云画布形态,"
                     f"现在{now_pct:.0f}% → 届时约{burn_pct:.0f}%")
        elif upstream_overcast and burn_pct <= now_pct + 5:
            trend = (f"现在{now_pct:.0f}%,但光路上游100-300km连续云盖压境,"
                     f"届时云量大概率上行,外推值{burn_pct:.0f}%仅供下限参考")
        elif not extrap_ok:
            trend = (f"现在{now_pct:.0f}%;位移估计峰质量低(多层云异动或"
                     f"原地生消),外推不可信,届时云量按现值加大不确定看待")
        else:
            trend = f"现在{now_pct:.0f}% → 届时约{burn_pct:.0f}%"
        meta = {"overcast": overcast, "lid": stats["lid"],
                "max_bt": stats["max_bt"], "mean_bt": stats["mean_bt"],
                "raw_pct": stats["pct"], "upstream_overcast": upstream_overcast,
                "visible_attached": vis_attached,
                "shift_response": None if resp is None else round(resp, 4),
                "extrap_trusted": extrap_ok,
                "frame_time": ts1.isoformat(timespec="minutes")}
        return round(now_pct, 1), round(burn_pct, 1), trend, frames, meta
    except (httpx.HTTPError, OSError):
        return None, None, None, [], None


def _upstream_overcast(frame, azimuth_deg: float, month: int) -> bool:
    """光路上游 100/200/300km 三窗是否全满盖(平流压境预警)。

    像素尺度按帧几何近似(北京纬度 B13 斜视:东西≈2.4km/px、南北≈3.2km/px,
    2026-07-09 复盘实测;旧名义值 2.0 低估 20-60%)。
    """
    from skyfire.cloudiness import box_stats as _bs
    import math
    km_x, km_y = 2.4, 3.2
    rad = math.radians(azimuth_deg)
    cx, cy = frame.center_px
    hits = 0
    for dist in (100, 200, 300):
        px = round(cx + math.sin(rad) * dist / km_x)
        py = round(cy - math.cos(rad) * dist / km_y)
        s = _bs(frame.gray, (px, py), half=20, month=month)
        if s is not None and s["lid"]:   # 暖顶云墙压境才算;冷卷云幕是画布不预警
            hits += 1
    return hits == 3


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
    sat_now, burn_pct, trend, live_frames, sat_meta = observe_burn_clouds(
        client, peak_utc, event, city.lat, city.lon, frames_dir,
        azimuth_deg=r.azimuth)
    # C1/outlook 距燃烧数小时以上:短时外推冒充不了届时云况
    # (knowledge §3.2:远期信预报当底子,临近才信实测外推),
    # 基线只用预报驱动的规则分;C2/C3/gated 临近才引入卫星外推修正。
    near = checkpoint not in ("c1", "outlook")
    cloud_args = (sat_now, burn_pct) if near else (None, None)

    # 模式硬分歧仲裁(2026-07-09:median(0,0,6,6)=3.0 是幻影场景):
    # 临近且实况可信时由卫星裁——满盖→悲观簇,画布实证→乐观簇;
    # 远期/实况不可信 → 保守偏置 + 低置信,禁止拿中间值拍板。
    split = detect_split(r.per_model)
    eff_index, eff_conf, split_note = r.index, r.confidence, None
    if split:
        eff_conf = "low"
        if near and sat_meta is not None:
            if sat_meta.get("lid"):
                eff_index = split["low"]
                split_note = (f"模式两簇分歧{split['gap']:.0f},卫星满盖暖顶盖子"
                              f"实证→取悲观簇{split['low']:.1f}")
            elif sat_now is not None and 25 <= sat_now <= 75:
                eff_index = split["high"]
                split_note = (f"模式两簇分歧{split['gap']:.0f},卫星画布实证"
                              f"→取乐观簇{split['high']:.1f}")
        if split_note is None:
            eff_index = round((split["low"] + (split["low"] + split["high"]) / 2)
                              / 2, 1)
            split_note = (f"模式两簇分歧{split['gap']:.0f}且实况未定"
                          f"→保守偏置{eff_index:.1f},双情景待临近确认")
    prob, qual = baseline_percent(eff_index, eff_conf, *cloud_args)
    # 各模式单独换算(用户要求推送分模型;也喂给 LLM 看模式间分歧)
    per_model_pct = {m: baseline_percent(s, eff_conf, *cloud_args)
                     for m, s in r.per_model.items()}

    # 因子过堂表:每个已知致错因子必须留痕(缺失≠沉默;2026-07-10 用户拍板)
    factors = _factor_sheet(r, checkpoint, sat_now, burn_pct, sat_meta,
                            split_note, trend)

    # 本场(date×city×event)已有预测 = 推送序号与"较上次"对比的依据;
    # 必须在 add_prediction 之前查,否则拿到的是本次自己
    prior = store.predictions_for(conn, str(day), city_key, event)
    if gate:
        last = prior[-1] if prior else None
        if not gate_exceeded(last["probability_pct"] if last else None, prob):
            return None

    now_utc = datetime.now(timezone.utc)
    hours_to_peak = round((peak_utc - now_utc).total_seconds() / 3600, 1)
    payload = {"date": str(day), "event": event, "checkpoint": checkpoint,
               "hours_to_peak": hours_to_peak,
               "rule_score": r.index, "confidence": r.confidence,
               "effective_rule_score": eff_index,
               "effective_confidence": eff_conf,
               "per_model": r.per_model,
               "per_model_raw": r.per_model_raw,
               "per_model_pct": per_model_pct,
               "aod": r.aod,
               "sat_cloud_now": sat_now, "burn_cloud_projected": burn_pct,
               "sat_meta": sat_meta,
               "trend": trend, "baseline_prob": prob, "baseline_quality": qual,
               "factor_sheet": factors}
    cases = store.cases_with_snapshot(conn, city_key, event, model="gfs_seamless")
    similar = similar_cases_from(cases, factor_vector(payload), k=3)
    llm_r = predict_pct(payload, similar, live_frames,
                        model=model or _pick_model())
    if llm_r is not None:
        rec = dict(probability_pct=llm_r["probability_pct"],
                   quality_pct=llm_r["quality_pct"],
                   confidence=llm_r["confidence"], llm_status="done",
                   reasoning=llm_r["reasoning"], risks=llm_r["risks"],
                   llm_factors=llm_r.get("factors"),
                   scenario_alt=llm_r.get("scenario_alt") or None)
    else:
        rec = dict(probability_pct=prob, quality_pct=qual,
                   confidence=eff_conf, llm_status="pending",
                   reasoning=None, risks=None, llm_factors=None,
                   scenario_alt=None)
    prev = None
    if prior:
        p_last = prior[-1]
        prev = {"probability_pct": p_last["probability_pct"],
                "quality_pct": p_last["quality_pct"],
                "checkpoint": p_last["checkpoint"],
                "time_local": None, "minutes_ago": None}
        try:
            prev_utc = datetime.strptime(
                p_last["created_at"], "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
            prev["time_local"] = prev_utc.astimezone(
                ZoneInfo(city.timezone)).strftime("%H:%M")
            prev["minutes_ago"] = round(
                (now_utc - prev_utc).total_seconds() / 60)
        except (ValueError, TypeError):
            pass  # created_at 异常:退化为只报数值差,不影响推送
    per_model_json = json.dumps(
        {m: {"prob": p, "qual": q, **r.per_model_raw.get(m, {})}
         for m, (p, q) in per_model_pct.items()}, ensure_ascii=False)
    pred_id = store.add_prediction(
        conn, str(day), city_key, event, checkpoint,
        probability_pct=rec["probability_pct"], quality_pct=rec["quality_pct"],
        confidence=rec["confidence"], rule_score=r.index,
        sat_cloud_pct=sat_now, trend=trend, llm_status=rec["llm_status"],
        reasoning=rec["reasoning"], risks=rec["risks"],
        per_model_json=per_model_json,
        factors_json=json.dumps(
            {"sheet": factors, "llm": rec.get("llm_factors"),
             "rules_applied": (llm_r or {}).get("rules_applied", [])},
            ensure_ascii=False))
    return {**rec, "id": pred_id, "date": str(day), "city": city_key,
            "event": event, "checkpoint": checkpoint, "rule_score": r.index,
            "sat_cloud_pct": sat_now, "trend": trend, "peak": r.peak,
            "per_model_pct": per_model_pct, "per_model_raw": r.per_model_raw,
            "aod": r.aod, "city_name": city.name,
            "seq": len(prior) + 1,
            "minutes_to_peak": round((peak_utc - now_utc).total_seconds() / 60),
            "generated_at": now_utc.astimezone(ZoneInfo(city.timezone)),
            "prev": prev, "factor_sheet": factors}


def _factor_sheet(r: PredictionResult, checkpoint: str,
                  sat_now: float | None, burn_pct: float | None,
                  sat_meta: dict | None, split_note: str | None,
                  trend: str | None) -> list[dict]:
    """因子过堂表:已知致错因子逐项留痕,缺失必须显式说代价(2026-07-10 拍板:
    教训只有写成每次强制执行的代码才算学会;缺失≠中性≠沉默)。"""
    f: list[dict] = []
    # 卫星实况
    if sat_now is None:
        f.append({"name": "卫星实况", "status": "缺失",
                  "note": "无实况校验,临近判断可信度打折"})
    elif sat_meta and sat_meta.get("lid"):
        f.append({"name": "卫星实况", "status": "满盖修正",
                  "note": f"线性读数{sat_meta['raw_pct']:.0f}%为暖顶假象,"
                          f"按{sat_now:.0f}%满盖计(最暖{sat_meta['max_bt']:.0f}K)"})
    elif sat_meta and sat_meta.get("overcast"):
        f.append({"name": "卫星实况", "status": "冷幕满盖",
                  "note": f"满盖但为冷云幕(高云画布形态),实测{sat_now:.0f}%不按闷盖处理"})
    else:
        f.append({"name": "卫星实况", "status": "正常",
                  "note": f"实测{sat_now:.0f}% 外推{burn_pct:.0f}%"})
    if sat_meta and sat_meta.get("upstream_overcast"):
        f.append({"name": "平流预警", "status": "触发",
                  "note": "光路上游100-300km连续云盖压境,外推值只当下限"})
    # 气溶胶
    if r.aod is None:
        f.append({"name": "气溶胶", "status": "缺失",
                  "note": "按0.85保守系数计,空气数据缺失"})
    else:
        f.append({"name": "气溶胶", "status": "正常", "note": f"AOD {r.aod}"})
    # 通道(含中云墙)
    if r.channel_empty:
        f.append({"name": "透光通道", "status": "缺失",
                  "note": "通道剖面无数据,置信度打折"})
    else:
        f.append({"name": "透光通道", "status": "正常",
                  "note": f"{r.blocked_points}点受阻(低云>60或中云>70),"
                          f"系数{r.channel_factor}"})
    # 模式分歧
    if split_note:
        f.append({"name": "模式分歧", "status": "硬分歧", "note": split_note})
    else:
        f.append({"name": "模式分歧", "status": "正常",
                  "note": f"极差{r.spread},{r.confidence}"})
    # 外推纪律
    if checkpoint in ("c1", "outlook"):
        f.append({"name": "外推纪律", "status": "远期",
                  "note": "距峰值数小时,实况外推不入基线,以预报为底"})
    elif trend:
        status = "临近"
        if sat_meta and not sat_meta.get("extrap_trusted", True):
            status = "外推不可信"
        f.append({"name": "外推纪律", "status": status, "note": trend})
    return f


def _pick_model() -> str:
    # 用户 2026-07-05 拍板:日常检查点用 Sonnet 5(Haiku 推理深度不够,
    # 曾把干冷气团方向猜反;Sonnet 读图接近 Opus,月成本仍 <$6)。
    return MODEL_DEEP
