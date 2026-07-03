"""云海规则评分(spec 5.2,MVP 简化:辐射雾/低层云生成条件)。

加分制,满分 10:晴夜辐射降温 3 + 近饱和 2.5 + 静风 2 +
温度露点差 1 + 日出时低云存在 1.5。阈值待回测校准。
另有两条物理门槛(不加分,只清零):大风(≥5 m/s)吹散辐射雾 →
近饱和分清零;空气太干(RH<85%)雾无从生成 → 静风分清零。
"""
from dataclasses import dataclass


@dataclass
class CloudSeaInputs:
    night_cloud_avg: float        # 前夜 22:00-04:00 平均总云量 %
    dawn_rh: float                # 日出时 2m 相对湿度 %
    dawn_wind: float              # 日出时 10m 风速 m/s
    dawn_temp_dew_spread: float   # 日出时 T - Td (°C)
    dawn_cloud_low: float         # 日出时低云量 %


@dataclass
class CloudSeaScore:
    score: float
    parts: dict[str, float]


def cloud_sea_score(inp: CloudSeaInputs) -> CloudSeaScore:
    parts: dict[str, float] = {}
    if inp.night_cloud_avg < 30:
        parts["radiative_cooling"] = 3.0
    elif inp.night_cloud_avg < 60:
        parts["radiative_cooling"] = 1.5
    else:
        parts["radiative_cooling"] = 0.0
    if inp.dawn_rh >= 95:
        parts["saturation"] = 2.5
    elif inp.dawn_rh >= 90:
        parts["saturation"] = 1.5
    else:
        parts["saturation"] = 0.0
    if inp.dawn_wind < 3:
        parts["calm_wind"] = 2.0
    elif inp.dawn_wind < 5:
        parts["calm_wind"] = 1.0
    else:
        parts["calm_wind"] = 0.0
    if inp.dawn_temp_dew_spread <= 2:
        parts["dew_spread"] = 1.0
    else:
        parts["dew_spread"] = 0.0
    if 20 <= inp.dawn_cloud_low <= 90:
        parts["low_cloud_present"] = 1.5
    else:
        parts["low_cloud_present"] = 0.0

    # 物理门槛:大风搅散辐射雾;空气太干雾根本起不来
    if inp.dawn_wind >= 5:
        parts["saturation"] = 0.0
    if inp.dawn_rh < 85:
        parts["calm_wind"] = 0.0

    total = round(min(10.0, sum(parts.values())), 1)
    return CloudSeaScore(score=total, parts=parts)
