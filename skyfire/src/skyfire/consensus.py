"""多模式一致性:分歧宽度 → 置信度(spec 5.3)。"""
from dataclasses import dataclass


@dataclass
class Consensus:
    index: float                 # 共识指数(各模式均值)
    per_model: dict[str, float]
    spread: float                # max - min
    confidence: str              # high / medium / low / degraded


def consensus(per_model: dict[str, float]) -> Consensus:
    values = list(per_model.values())
    index = round(sum(values) / len(values), 1)
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
