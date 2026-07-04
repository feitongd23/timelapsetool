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


from datetime import timedelta, timezone

import httpx
from PIL import Image

from skyfire import store
from skyfire.config import City
from skyfire.consensus import consensus
from skyfire.himawari import fetch_region, round_down_10min
from skyfire.openmeteo import fetch_point_forecast_range
from skyfire.scoring.firecloud import FireCloudInputs, fire_cloud_score
from skyfire.suntimes import sun_window


@dataclass
class BackfillResult:
    case_id: int
    n_frames: int
    n_models: int


def backfill_row(conn, client: httpx.Client, row: BackfillRow, city: City,
                 frames_dir, n_frames: int = 3) -> BackfillResult:
    """单条清单 → 完整案例:历史多模式快照 + 规则分重算 + 卫星帧(尽力)。

    冷启动无通道剖面与 AOD(历史点阵回填成本高,留观)——规则分以
    canvas/本地因子为主,channel=[] 走 firecloud 的"缺数据不罚"路径;
    检索层(rag)对缺失字段做中性处理。
    """
    day = date_type.fromisoformat(row.date)
    # cloud_sea 属日出前后的天象,取 sunrise 窗回填
    win = sun_window(city.lat, city.lon, city.timezone, day,
                     "sunrise_glow" if row.event == "cloud_sea" else row.event)
    iso_hour = win.peak.strftime("%Y-%m-%dT%H:00")

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
            aod=None, channel=[],
        ))
        per_model[fc.model] = r.score
    rule = consensus(per_model).index if per_model else None
    conf = consensus(per_model).confidence if per_model else None

    case_id = store.upsert_case(conn, row.date, row.city, row.event,
                                rule_score=rule, confidence=conf, source="cold_start")
    store.set_actual_score(conn, case_id, row.score)
    for fc in forecasts:
        h = fc.at(iso_hour)
        if h is None:
            continue
        store.add_snapshot(conn, case_id, fc.model, {
            "hour": iso_hour, "cloud_high": h.cloud_high, "cloud_mid": h.cloud_mid,
            "cloud_low": h.cloud_low, "cloud_cover": h.cloud_cover,
            "rh_2m": h.rh_2m, "precipitation": h.precipitation, "aod": None,
            "channel": [], "azimuth": round(win.azimuth_deg, 1),
        })

    frames_dir = Path(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    peak_utc = win.peak.astimezone(timezone.utc)
    saved = 0
    for k in range(n_frames):
        ts = round_down_10min(peak_utc - timedelta(minutes=30 * k))
        try:
            frame = fetch_region(client, "infrared", ts, city.lat, city.lon)
        except httpx.HTTPError:
            continue
        if frame.gray.max() == 0:
            continue  # 全缺瓦片视为无档
        path = frames_dir / f"{row.city}_{row.date}_{row.event}_{ts:%H%M}.png"
        Image.fromarray(frame.gray, mode="L").save(path)
        store.add_satellite_frame(conn, case_id, ts.isoformat(), "infrared", str(path))
        saved += 1
    return BackfillResult(case_id=case_id, n_frames=saved, n_models=len(per_model))
