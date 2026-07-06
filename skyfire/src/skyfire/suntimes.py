from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from astral import Observer
from astral.sun import azimuth, dawn, dusk, sunrise, sunset


@dataclass
class SunWindow:
    event: str            # "sunrise_glow" | "sunset_glow"
    peak: datetime        # 日出/日落时刻(本地时区)
    window_start: datetime
    window_end: datetime
    azimuth_deg: float    # peak 时刻太阳方位角(光通道方向)


def sun_window(lat: float, lon: float, tz: str, day: date, event: str) -> SunWindow:
    obs = Observer(latitude=lat, longitude=lon)
    tzinfo = ZoneInfo(tz)
    if event == "sunset_glow":
        peak = sunset(obs, day, tzinfo=tzinfo)
        start, end = peak.replace(minute=0), dusk(obs, day, tzinfo=tzinfo)
    elif event == "sunrise_glow":
        peak = sunrise(obs, day, tzinfo=tzinfo)
        start, end = dawn(obs, day, tzinfo=tzinfo), peak
    else:
        raise ValueError(f"unknown event: {event}")
    return SunWindow(
        event=event, peak=peak, window_start=start, window_end=end,
        azimuth_deg=azimuth(obs, peak),
    )


def nearest_iso_hour(dt: datetime) -> str:
    """就近取整到小时的 ISO 串(04:47→05:00)。

    预报按整点给数;此前用 strftime 截断,峰值 xx:30 之后取数偏差近一小时。
    """
    if dt.minute >= 30:
        dt = dt + timedelta(hours=1)
    return dt.strftime("%Y-%m-%dT%H:00")
