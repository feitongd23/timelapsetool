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


def canvas_score(cloud_high: float, cloud_mid: float,
                 cloud_low: float = 0.0) -> float:
    """画布云:高云全权重、中云半权重;40-70% 覆盖最佳。

    >70 的"满盖"惩罚只对中低云主导的闷盖生效:纯高云满天(卷层云幕)
    是被染透的最佳画布,不按阴天归零(2026-07-07 中大烧漏报根因 #1——
    EC/ICON 正确报高云 100% 反被打 0 分)。
    """
    canvas = cloud_high + 0.5 * cloud_mid
    if canvas < 5:
        return 0.0
    if canvas < 40:
        return round(10 * (canvas - 5) / 35, 2)
    if canvas <= 70:
        return 10.0
    blocker = cloud_mid + cloud_low          # 真正遮光的层
    if blocker <= 30:
        return 10.0                          # 高云主导的满盖:满分画布
    over = min(1.0, (canvas - 70) / 30)
    damp = min(1.0, (blocker - 30) / 40)
    return round(10 * (1 - over * damp), 2)


def channel_factor(channel: list[ChannelPoint]) -> tuple[float, int]:
    """通道透光:100-400km 采样点,低云>60% 视为堵。
    半数以上堵 → 一票否决(0.1)。缺数据的点不计。

    只看低云不看总云:高云盖顶不挡日落平射光(knowledge §3.2,与 llm
    提示词口径一致)。旧判据 cloud_total>85 曾把纯高云通道误判为堵,
    是 2026-07-07 中午 c1 3%/3% 误导推送的根因 #2。
    """
    scored = [p for p in channel if 100 <= p.dist_km <= 400
              and p.cloud_low is not None]
    if not scored:
        return 1.0, 0
    blocked = sum(1 for p in scored if p.cloud_low > 60)
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
    canvas = canvas_score(inp.cloud_high, inp.cloud_mid, inp.cloud_low)
    ch_factor, blocked = channel_factor(inp.channel)
    score = (canvas * ch_factor * local_low_factor(inp.cloud_low)
             * aerosol_factor(inp.aod) * precip_factor(inp.precipitation))
    return FireCloudScore(
        score=round(score, 1), canvas=canvas,
        channel_factor=ch_factor, blocked_points=blocked,
    )
