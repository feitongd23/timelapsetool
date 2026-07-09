from dataclasses import dataclass


@dataclass
class HourlyPoint:
    time: str                     # "2026-07-03T19:00"(城市本地时区)
    cloud_cover: float | None
    cloud_low: float | None
    cloud_mid: float | None
    cloud_high: float | None
    rh_2m: float | None
    wind_speed: float | None      # m/s
    temperature: float | None     # °C
    dew_point: float | None       # °C
    precipitation: float | None   # mm


@dataclass
class ModelForecast:
    model: str
    hourly: list[HourlyPoint]

    def at(self, iso_hour: str) -> HourlyPoint | None:
        for h in self.hourly:
            if h.time == iso_hour:
                return h
        return None


@dataclass
class ChannelPoint:
    dist_km: float
    cloud_low: float | None
    cloud_total: float | None
    # 2026-07-09 复盘:西北中云墙压死光路却因只采低云被判"畅通"——通道必须看中云
    cloud_mid: float | None = None
