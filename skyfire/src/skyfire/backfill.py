"""经验库冷启动回填(spec 6.1):CSV 清单 → 历史预报快照 + 历史卫星帧。"""
import csv
from dataclasses import dataclass
from datetime import date as date_type
from pathlib import Path

VALID_EVENTS = ("sunrise_glow", "sunset_glow", "cloud_sea")


@dataclass
class BackfillRow:
    date: str
    city: str
    event: str
    score: float


def parse_csv(path: Path) -> list[BackfillRow]:
    rows: list[BackfillRow] = []
    with open(path, newline="", encoding="utf-8") as f:
        for i, rec in enumerate(csv.DictReader(f), start=2):
            date_s = (rec.get("date") or "").strip()
            try:
                date_type.fromisoformat(date_s)
            except ValueError:
                raise ValueError(f"第 {i} 行:日期格式应为 YYYY-MM-DD,收到 {date_s!r}")
            event = (rec.get("event") or "").strip()
            if event not in VALID_EVENTS:
                raise ValueError(f"第 {i} 行:未知天象 {event!r},可用: {', '.join(VALID_EVENTS)}")
            try:
                score = float((rec.get("score") or "").strip())
            except ValueError:
                raise ValueError(f"第 {i} 行:score 必须是数字")
            if not 0 <= score <= 10:
                raise ValueError(f"第 {i} 行:score 必须在 0-10,收到 {score}")
            rows.append(BackfillRow(date=date_s, city=(rec.get("city") or "").strip(),
                                    event=event, score=score))
    return rows


from datetime import timezone

import httpx

from skyfire import store
from skyfire.config import City
from skyfire.consensus import consensus
from skyfire.geo import channel_points
from skyfire.himawari_hsd import fetch_case_frames, observer_cloudiness
from skyfire.openmeteo import (fetch_aod_range, fetch_channel_profile_range,
                               fetch_point_forecast_range)
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score
from skyfire.suntimes import nearest_iso_hour, sun_window


@dataclass
class BackfillResult:
    case_id: int
    n_frames: int
    n_models: int


def backfill_row(conn, client: httpx.Client, row: BackfillRow, city: City,
                 frames_dir) -> BackfillResult:
    """单条清单 → 完整案例:历史快照 + 真实通道/AOD + AWS 卫星帧。

    通道剖面与 AOD 走历史存档(尽力,失败→中性);帧走 AWS HSD 归档
    (ir×4 + vis×2,单帧缺档跳过)。幂等:重跑覆盖快照分、帧去重。
    """
    day = date_type.fromisoformat(row.date)
    win = sun_window(city.lat, city.lon, city.timezone, day,
                     "sunrise_glow" if row.event == "cloud_sea" else row.event)
    iso_hour = nearest_iso_hour(win.peak)

    pts = channel_points(city.lat, city.lon, win.azimuth_deg)
    try:
        channel = fetch_channel_profile_range(client, pts, city.timezone,
                                              iso_hour, row.date)
    except httpx.HTTPError:
        channel = []                       # 存档边界外:退回"缺数据不罚"
    aod = fetch_aod_range(client, city.lat, city.lon, city.timezone,
                          iso_hour, row.date)

    forecasts = fetch_point_forecast_range(client, city.lat, city.lon, city.timezone,
                                           row.date, row.date)
    per_model: dict[str, float] = {}
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
    rule = consensus(per_model).index if per_model else None
    conf = consensus(per_model).confidence if per_model else None

    case_id = store.upsert_case(conn, row.date, row.city, row.event,
                                rule_score=rule, confidence=conf, source="cold_start")
    store.set_actual_score(conn, case_id, row.score)
    store.clear_snapshots(conn, case_id)
    channel_json = [{"km": p.dist_km, "low": p.cloud_low, "total": p.cloud_total}
                    for p in channel]
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None:
            continue
        store.add_snapshot(conn, case_id, fc.model, {
            "hour": iso_hour, "cloud_high": h.cloud_high, "cloud_mid": h.cloud_mid,
            "cloud_low": h.cloud_low, "cloud_cover": h.cloud_cover,
            "rh_2m": h.rh_2m, "precipitation": h.precipitation, "aod": aod,
            "channel": channel_json, "azimuth": round(win.azimuth_deg, 1),
        })

    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    peak_utc = win.peak.astimezone(timezone.utc)
    prefix = f"{row.city}_{row.date}_{row.event}"
    saved = 0
    frame_event = "sunrise_glow" if row.event == "cloud_sea" else row.event
    frames = fetch_case_frames(client, peak_utc, frames_dir, prefix=prefix,
                               event=frame_event, lat=city.lat, lon=city.lon,
                               azimuth_deg=win.azimuth_deg)
    for ts, ch, path in frames:
        store.add_satellite_frame(conn, case_id, ts.isoformat(), ch, str(path))
        saved += 1

    sat_pct = observer_cloudiness(client, peak_utc, frame_event,
                                  city.lat, city.lon)
    if sat_pct is not None:
        store.set_sat_cloud(conn, case_id, sat_pct)
    return BackfillResult(case_id=case_id, n_frames=saved, n_models=len(per_model))
