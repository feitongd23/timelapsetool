"""免费层 → 概率%/质量% 基线(spec §3;初版简单可解释,回测迭代)。

质量% = 规则分×10;概率% = 质量% × 一致性系数,再按燃烧时刻云量修正:
甜区(30-70)+15;<15 或 >90(没画布/满盖)封顶 20。云量取外推值,
缺则实测,再缺不修正(knowledge §3.2:燃烧时刻云量以卫星实测/外推为准)。
"""

_CONF_FACTOR = {"high": 1.0, "medium": 0.85, "low": 0.7, "degraded": 0.6}


def _clamp(v: float) -> int:
    return int(round(max(0.0, min(100.0, v))))


def baseline_percent(rule_score: float, confidence: str,
                     sat_cloud_pct: float | None,
                     projected_cloud_pct: float | None) -> tuple[int, int]:
    quality = _clamp(rule_score * 10)
    prob = quality * _CONF_FACTOR.get(confidence, 0.6)
    cloud = projected_cloud_pct if projected_cloud_pct is not None else sat_cloud_pct
    if cloud is not None:
        if cloud < 15 or cloud > 90:
            prob = min(prob, 20.0)
        elif 30 <= cloud <= 70:
            prob += 15
    return _clamp(prob), quality
