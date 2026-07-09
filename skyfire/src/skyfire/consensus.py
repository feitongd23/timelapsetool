"""多模式一致性:分歧宽度 → 置信度(spec 5.3)。

共识指数用中位数:算术平均会被单模式的规则性零分拖垮(2026-07-07
漏报根因 #4——四模式 0.5/0.8/0/0 把均值压到 0.3)。可传 weights
(来自 model_skill 账本,见 skill.py):样本攒够后按各模式历史准确度
加权平均,自动偏向常态更准的模式。
"""
from dataclasses import dataclass
from statistics import median


@dataclass
class Consensus:
    index: float                 # 共识指数(中位数;有 skill 权重时加权平均)
    per_model: dict[str, float]
    spread: float                # max - min
    confidence: str              # high / medium / low / degraded


def detect_split(per_model: dict[str, float],
                 gap: float = 4.0) -> dict | None:
    """2v2 式硬分歧检测(2026-07-09 根因:median(0,0,6,6)=3.0 是四家谁都
    没预报过的"半烧"幻影场景)。

    排序后相邻极差 ≥gap(0-10 分制,默认 4=40pp)视为两簇硬分歧,返回
    {"low": 悲观簇中位数, "high": 乐观簇中位数, "gap": 缺口}——由调用方
    用卫星实况仲裁(满盖→悲观簇,画布实证→乐观簇;实况不可信→双情景+低置信,
    禁止拿中间值拍板)。分歧不足或样本<4 返回 None。
    """
    if len(per_model) < 4:
        return None
    vals = sorted(per_model.values())
    gaps = [(vals[i + 1] - vals[i], i) for i in range(len(vals) - 1)]
    g, i = max(gaps)
    if g < gap:
        return None
    lo, hi = vals[:i + 1], vals[i + 1:]
    return {"low": round(median(lo), 1), "high": round(median(hi), 1),
            "gap": round(g, 1)}


def consensus(per_model: dict[str, float],
              weights: dict[str, float] | None = None) -> Consensus:
    values = list(per_model.values())
    total = (sum(weights[m] for m in per_model)
             if weights and all(m in weights for m in per_model) else 0.0)
    if total > 0:
        index = round(sum(s * weights[m] for m, s in per_model.items())
                      / total, 1)
    else:
        index = round(median(values), 1)
    spread = round(max(values) - min(values), 1)
    if len(values) < 2:
        confidence = "degraded"
    elif spread <= 1.5:
        confidence = "high"
    elif spread <= 3.0:
        confidence = "medium"
    else:
        confidence = "low"
    return Consensus(index=index, per_model=per_model, spread=spread, confidence=confidence)
