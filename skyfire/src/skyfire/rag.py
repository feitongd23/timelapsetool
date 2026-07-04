"""相似案例检索(spec 5.5):因子向量 + 欧氏距离,零第三方依赖。"""
import math

_SCALES = {"cloud_high": 100.0, "cloud_mid": 100.0, "cloud_low": 100.0,
           "rh_2m": 100.0, "aod": 1.0}


def factor_vector(payload: dict) -> list[float]:
    """快照 payload → 7 维归一化向量。

    [高云, 中云, 低云, 湿度, AOD, 通道受堵比, 季节(月份余弦)]
    缺失字段取中性值,保证冷启动案例(无 AOD/通道)可比。
    """
    v = []
    for key in ("cloud_high", "cloud_mid", "cloud_low", "rh_2m"):
        raw = payload.get(key)
        v.append((raw if raw is not None else 0.0) / _SCALES[key])
    aod = payload.get("aod")
    v.append(min(aod / _SCALES["aod"], 1.5) if aod is not None else 0.5)
    channel = payload.get("channel") or []
    scored = [p for p in channel if p.get("low") is not None and p.get("total") is not None]
    if scored:
        blocked = sum(1 for p in scored if p["low"] > 60 or p["total"] > 85) / len(scored)
    else:
        blocked = 0.0
    v.append(blocked)
    month = int(str(payload.get("hour", "2026-06-15"))[5:7])
    v.append((math.cos((month - 1) / 12 * 2 * math.pi) + 1) / 2)
    return v


def similar_cases_from(cases: list[dict], target: list[float], k: int = 3) -> list[dict]:
    ranked = []
    for c in cases:
        vec = factor_vector(c["payload"])
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(vec, target)))
        ranked.append({**c, "distance": round(dist, 4)})
    ranked.sort(key=lambda c: c["distance"])
    return ranked[:k]
