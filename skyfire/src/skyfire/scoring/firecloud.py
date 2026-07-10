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
    """通道透光:100-400km 采样点,低云>60% 或中云>70% 视为堵。
    半数以上堵 → 一票否决(0.1)。缺数据的点不计。

    高云盖顶不挡日落平射光(knowledge §3.2)——旧判据 cloud_total>85
    曾把纯高云通道误判为堵(2026-07-07 根因 #2);但厚中云墙确实挡
    (2026-07-09 0分实锤:300.4°光路 total 76-100% 全程闷盖、low 全 0,
    "只看低云"判成畅通,用户目视西北连续乌云=中低云墙)。中云缺数据
    (旧快照)时该点只按低云判,不虚构。
    采样含 50km 近程点(规则 channel-directional-hard-gate 裁决:2026-07-05
    案例 50km 低云满盖堵进光口却不在旧 100-400km 窗内)。
    采样点正在降雨(≥0.5mm/h)也判堵:雨幕从云底拖到地面,光穿不过
    (2026-07-10 用户实锤:呼市-吕梁-西安雨带横在济青一线日落光路上,
    该线可能性应为 0,而旧判据对光路降雨视而不见)。
    """
    scored = [p for p in channel if 50 <= p.dist_km <= 400
              and p.cloud_low is not None]
    if not scored:
        return 1.0, 0
    blocked = sum(1 for p in scored
                  if p.cloud_low > 60
                  or (p.cloud_mid is not None and p.cloud_mid > 70)
                  or (p.precip is not None and p.precip >= 0.5))
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
    """缺失≠中性(2026-07-09 复盘:AOD 实况 1.4 从未进链,manual 版填 None
    一路畅通拿 1.0)——缺数据按轻度浑浊 0.85 保守计,推送须标'空气数据缺失'。"""
    if aod is None:
        return 0.85
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
