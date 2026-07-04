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
