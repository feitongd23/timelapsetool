"""调度打点:判断当前时刻该推哪些城市×天象(spec 5.4 临近/推送窗口)。

纯函数,不碰 DB;去重由调用方用 store.was_pushed 完成。
对每个城市各算今日与明日的日落/日出峰值,取"现在到峰值 <= lead 且 >= 0"者。
跨 UTC 日界的日出用两天候选覆盖。
"""
from datetime import datetime, timedelta, timezone

from skyfire.config import City
from skyfire.suntimes import sun_window

EVENTS = ("sunset_glow", "sunrise_glow")


def due_events(cities: dict[str, City], now: datetime,
               lead_minutes: int = 120) -> list[tuple[str, str]]:
    now_utc = now.astimezone(timezone.utc)
    due: list[tuple[str, str]] = []
    for key, c in cities.items():
        for event in EVENTS:
            # 候选:以城市本地时区的今日与明日各算一次,覆盖 UTC 日界
            for day_offset in (0, 1):
                local_day = (now_utc.astimezone(_tz(c)) + timedelta(days=day_offset)).date()
                win = sun_window(c.lat, c.lon, c.timezone, local_day, event)
                peak_utc = win.peak.astimezone(timezone.utc)
                delta_min = (peak_utc - now_utc).total_seconds() / 60
                if 0 <= delta_min <= lead_minutes:
                    due.append((key, event))
                    break
    return due


def _tz(c: City):
    from zoneinfo import ZoneInfo
    return ZoneInfo(c.timezone)
