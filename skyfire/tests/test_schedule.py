from datetime import datetime, timezone
from pathlib import Path

from skyfire.config import load_cities
from skyfire.schedule import due_events

CONFIG = Path(__file__).parent.parent / "config" / "cities.yaml"


def test_due_events_inside_sunset_lead_window():
    cities = load_cities(CONFIG)
    # 北京 2026-06-21 日落约 19:46 CST = 11:46 UTC;取前 2 小时窗口内的 10:30 UTC
    now = datetime(2026, 6, 21, 10, 30, tzinfo=timezone.utc)
    due = due_events(cities, now, lead_minutes=120)
    assert ("beijing", "sunset_glow") in due


def test_due_events_before_window_empty():
    cities = load_cities(CONFIG)
    # 距日落还有 5 小时(06:46 UTC),不在前 2 小时窗口
    now = datetime(2026, 6, 21, 6, 46, tzinfo=timezone.utc)
    due = due_events(cities, now, lead_minutes=120)
    assert ("beijing", "sunset_glow") not in due


def test_due_events_after_peak_empty():
    cities = load_cities(CONFIG)
    # 日落后(12:30 UTC = 20:30 CST),已过峰值
    now = datetime(2026, 6, 21, 12, 30, tzinfo=timezone.utc)
    due = due_events(cities, now, lead_minutes=120)
    assert ("beijing", "sunset_glow") not in due


def test_due_events_matches_sunrise_window():
    cities = load_cities(CONFIG)
    # 北京 2026-06-21 日出约 04:46 CST = 2026-06-20 20:46 UTC;前 2 小时 = 19:30 UTC
    now = datetime(2026, 6, 20, 19, 30, tzinfo=timezone.utc)
    due = due_events(cities, now, lead_minutes=120)
    assert ("beijing", "sunrise_glow") in due
