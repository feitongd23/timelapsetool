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
    # 盖子检查前置(2026-07-11 F7:high0/mid99.6/low100 的降雨闷盖曾以
    # canvas=49.8 从 40-70 分支拿满分——纯中低云满盖是盖子不是画布)
    if cloud_high < 20 and (cloud_mid + cloud_low) >= 90:
        return 2.0
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


def channel_factor(channel: list[ChannelPoint], *,
                   rain_veto: float = 1.0,
                   rain_soft: float = 0.5) -> tuple[float, int]:
    """通道透光。2026-07-11 对抗审计重构(F2/F3/F4/F13):否决必须是真否决。

    判据分段(光线高度几何:距离越远,光线越高,低云已在光路之下):
    - 25-400km 近段:低云>60 或 中云>70 或 降雨≥rain_soft 判堵;
    - 400-800km 远段:只判 降雨≥rain_soft 或 中云≥85(防远段过杀,
      保住"高云画布西缘在远处"的教科书甜区)。
    硬短路(比例制之前):
    - 任一点降雨≥rain_veto → 系数 0(雨墙是从云底拖到地面的不透明实体,
      光路穿过它是全堵不是按比例衰减;用户 2026-07-10 实锤);
    - 任一点降雨≥rain_soft → 系数封顶 0.1;
    - 近段相邻两点低云≥85(=50km 连续低云墙)→ 系数封顶 0.1。
    缺数据≠畅通(规则 channel-missing-data-not-open):全缺 → 0.6;
    有效点不足一半(如图西边界走廊越界)→ 系数×0.85 覆盖惩罚。
    高云盖顶仍不算堵(knowledge §3.2,2026-07-07 根因 #2 的修正保留)。
    """
    usable = [p for p in channel
              if p.cloud_low is not None or p.precip is not None]
    scored = [p for p in usable if 25 <= p.dist_km <= 800]
    if not scored:
        return 0.6, 0   # 未知≠畅通:通道是硬门槛,盲区按明显打折计

    def _blk(p: ChannelPoint) -> bool:
        rain = p.precip is not None and p.precip >= rain_soft
        if p.dist_km > 400:
            return rain or (p.cloud_mid is not None and p.cloud_mid >= 85)
        return (rain or (p.cloud_low or 0) > 60
                or (p.cloud_mid is not None and p.cloud_mid > 70))

    blocked = sum(_blk(p) for p in scored)
    if any(p.precip is not None and p.precip >= rain_veto for p in scored):
        return 0.0, blocked
    frac = blocked / len(scored)
    factor = max(0.1, round(1 - 1.8 * frac, 2))
    if any(p.precip is not None and p.precip >= rain_soft for p in scored):
        factor = min(factor, 0.1)
    near = sorted((p for p in scored if p.dist_km <= 400),
                  key=lambda p: p.dist_km)
    for a, b in zip(near, near[1:]):
        if (a.cloud_low or 0) >= 85 and (b.cloud_low or 0) >= 85:
            factor = min(factor, 0.1)   # 50km 连续低云墙
            break
    if channel and len(scored) < len(channel) / 2:
        factor = round(factor * 0.85, 2)   # 覆盖不足惩罚(边界盲区诚实打折)
    return factor, blocked


def local_low_factor(cloud_low: float) -> float:
    """本地低云遮挡:低云盖顶时地面看不到高云画布。"""
    if cloud_low <= 40:
        return 1.0
    if cloud_low <= 70:
        return 0.7
    if cloud_low < 80:
        return 0.25
    return 0.1   # ≥80 遮死(2026-07-11 F11)


def aerosol_factor(aod: float | None) -> float:
    """缺失≠中性(2026-07-09 复盘:AOD 实况 1.4 从未进链,manual 版填 None
    一路畅通拿 1.0)——缺数据按 0.7 计(规则 aod-missing-not-neutral 用户
    拍板值;0.85 曾是半修状态,2026-07-11 F10 对齐),推送须标'空气数据缺失'。"""
    if aod is None:
        return 0.7
    if aod < 0.3:
        return 1.0
    if aod < 0.6:
        return 0.85
    if aod < 1.0:
        return 0.6
    return 0.3


def precip_factor(precipitation: float) -> float:
    """本地降水三档(2026-07-11 F3 对齐规则 precip-three-tier-gate):
    ≥1.0mm/h 一票否决归零;0.5-1.0 重罚;以下不罚(雨尾语境)。"""
    if precipitation >= 1.0:
        return 0.0
    if precipitation >= 0.5:
        return 0.2
    return 1.0


def fire_cloud_score(inp: FireCloudInputs, *,
                     rain_veto: float = 1.0,
                     rain_soft: float = 0.5) -> FireCloudScore:
    canvas = canvas_score(inp.cloud_high, inp.cloud_mid, inp.cloud_low)
    ch_factor, blocked = channel_factor(inp.channel, rain_veto=rain_veto,
                                        rain_soft=rain_soft)
    score = (canvas * ch_factor * local_low_factor(inp.cloud_low)
             * aerosol_factor(inp.aod) * precip_factor(inp.precipitation))
    return FireCloudScore(
        score=round(score, 1), canvas=canvas,
        channel_factor=ch_factor, blocked_points=blocked,
    )
