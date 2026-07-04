"""实况层评分与融合(spec 5.4:权重曲线 + 帧龄降级)。"""
from dataclasses import dataclass

MAX_FRAME_AGE_MIN = 40.0


@dataclass
class FusedScore:
    score: float          # 0-10 综合分
    obs: float            # 实况分
    weight: float         # 实况权重
    degraded: bool        # 帧龄超限 → 退回纯规则分


def obs_weight(minutes_to_window: float) -> float:
    """T-6h 30% → T-2h 60% → T-1h 起 85%(线性插值,spec 5.4)。"""
    m = minutes_to_window
    if m >= 360:
        return 0.3
    if m >= 120:
        return 0.3 + (360 - m) / 240 * 0.3
    if m >= 60:
        return 0.6 + (120 - m) / 60 * 0.25
    return 0.85


def obs_score(local_cloudiness: float, corridor_pred: list[float]) -> float:
    """实况分(0-10):本地有画布云 + 外推后走廊透光。

    红外代理无法分高低云,画布项刻意宽容;走廊项是主判据。阈值待回测校准。
    """
    if local_cloudiness < 5:
        canvas = 0.5
    elif local_cloudiness <= 80:
        canvas = 10.0
    else:
        canvas = 4.0
    if not corridor_pred:
        return round(canvas, 1)
    blocked = sum(1 for v in corridor_pred if v > 60) / len(corridor_pred)
    factor = max(0.1, 1 - 1.8 * blocked)
    return round(canvas * factor, 1)


def fuse(rule_score: float, observed: float, minutes_to_window: float,
         frame_age_min: float) -> FusedScore:
    if frame_age_min > MAX_FRAME_AGE_MIN:
        return FusedScore(score=rule_score, obs=observed, weight=0.0, degraded=True)
    w = obs_weight(minutes_to_window)
    return FusedScore(score=round(rule_score * (1 - w) + observed * w, 1),
                      obs=observed, weight=w, degraded=False)
