"""火烧云规则评分。

因子(spec 5.1):画布云、通道透光(一票否决级)、本地低云遮挡、
气溶胶、降水。所有阈值为初版经验值,待回测校准(spec 9)。
"""
from dataclasses import dataclass

from skyfire.models import ChannelPoint


@dataclass
class FireCloudInputs:
    cloud_high: float
    cloud_mid: float
    cloud_low: float
    precipitation: float
    aod: float | None
    channel: list[ChannelPoint]


@dataclass
class FireCloudScore:
    score: float             # 0-10
    canvas: float            # 画布分量 0-10
    channel_factor: float    # 0-1
    blocked_points: int      # 100-400km 内被堵采样点数


def canvas_score(cloud_high: float, cloud_mid: float) -> float:
    """画布云:高云全权重、中云半权重;40-70% 覆盖最佳。"""
    canvas = cloud_high + 0.5 * cloud_mid
    if canvas < 5:
        return 0.0
    if canvas < 40:
        return round(10 * (canvas - 5) / 35, 2)
    if canvas <= 70:
        return 10.0
    return round(max(0.0, 10 * (100 - canvas) / 30), 2)


def channel_factor(channel: list[ChannelPoint]) -> tuple[float, int]:
    """通道透光:100-400km 采样点,低云>60% 或总云>85% 视为堵。
    半数以上堵 → 一票否决(0.1)。缺数据的点不计。"""
    scored = [p for p in channel if 100 <= p.dist_km <= 400
              and p.cloud_low is not None and p.cloud_total is not None]
    if not scored:
        return 1.0, 0
    blocked = sum(1 for p in scored if p.cloud_low > 60 or p.cloud_total > 85)
    frac = blocked / len(scored)
    return max(0.1, round(1 - 1.8 * frac, 2)), blocked


def local_low_factor(cloud_low: float) -> float:
    """本地低云遮挡:低云盖顶时地面看不到高云画布。"""
    if cloud_low <= 40:
        return 1.0
    if cloud_low <= 70:
        return 0.7
    return 0.25


def aerosol_factor(aod: float | None) -> float:
    if aod is None:
        return 1.0  # 缺数据不惩罚,置信度由上层降级
    if aod < 0.3:
        return 1.0
    if aod < 0.6:
        return 0.85
    if aod < 1.0:
        return 0.6
    return 0.3


def precip_factor(precipitation: float) -> float:
    return 0.2 if precipitation > 0.5 else 1.0


def fire_cloud_score(inp: FireCloudInputs) -> FireCloudScore:
    canvas = canvas_score(inp.cloud_high, inp.cloud_mid)
    ch_factor, blocked = channel_factor(inp.channel)
    score = (canvas * ch_factor * local_low_factor(inp.cloud_low)
             * aerosol_factor(inp.aod) * precip_factor(inp.precipitation))
    return FireCloudScore(
        score=round(score, 1), canvas=canvas,
        channel_factor=ch_factor, blocked_points=blocked,
    )
